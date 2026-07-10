Attribute VB_Name = "CleanAndSummarize"
'==============================================================================
' Module : CleanAndSummarize
' Purpose: Replace the manual workflow of "download SAP export -> clean in Excel
'          -> summarize by hand" for the daily engine health report.
'
' ASML JD mapping:
'   "use macro to replace manual download from SAP, manual summary in excel"
'
' Lean waste eliminated:
'   Motion         -> no repeated importing, copy-pasting, window switching
'   Overprocessing -> cleaning and summary rules standardized, not redone daily
'   Defects        -> removes silent human error. Two examples in this data:
'                     (a) forgetting to TRIM equipment IDs splits one machine
'                         into two pivot rows
'                     (b) "Warning" vs "warning" vs "WARNING" splits the KPI
'                         into three categories and undercounts alerts
'
' Position in the pipeline:
'   01-core-model/scoring/score_engines.py  (VAE model scores every reading)
'        -> outputs/model_predictions.csv   (the "system output")
'        -> sample-data/SAP_EXPORT_*.csv    (dirty daily export, simulated)
'        -> THIS MACRO                      (clean + summarize)
'        -> Power Automate / Power BI        (distribute + visualize)
'
' The export contains the MODEL'S PREDICTION only. Ground-truth remaining useful
' life never appears here -- in reality the failure has not happened yet.
'
' Input layout (semicolon separated, 22 columns, 0-based index):
'   00 ExportDate   01 EquipmentID  02 Cycle       03 Timestamp
'   04..15 Sensor_2,3,4,7,8,9,11,12,13,14,15,17
'   16 LatentZ1     17 LatentZ2     18 NearestDistance
'   19 PredictedStatus              20 WorkOrder   21 MaintenanceCost
'
' Benefit measurement:
'   This macro records its own runtime with Timer and writes it to Summary!B9.
'   That value is the measured (green) input for 06-lean-lss/roi-validation.xlsx.
'
' NOTE: Comments and message strings are ASCII-only on purpose. The VBA editor
'       imports .bas files using the system ANSI code page, so non-ASCII text
'       would be corrupted. Chinese documentation lives in README.md.
'
' Usage:
'   1. Save the workbook as .xlsm inside the 02-automation-vba\ folder
'   2. Import this file into the VBA editor (Alt+F11 -> File -> Import File)
'   3. Run CleanAndSummarize (Alt+F8)
'==============================================================================
Option Explicit

Private Const DELIM As String = ";"     ' SAP exports commonly use semicolons,
                                        ' so thousand separators do not split fields
Private Const COL_COUNT As Long = 22

' 0-based column indexes into the split line
Private Const IX_DATE As Long = 0
Private Const IX_EQUIP As Long = 1
Private Const IX_CYCLE As Long = 2
Private Const IX_TS As Long = 3
Private Const IX_SENSOR_FIRST As Long = 4
Private Const IX_SENSOR_LAST As Long = 15
Private Const IX_Z1 As Long = 16
Private Const IX_Z2 As Long = 17
Private Const IX_DIST As Long = 18
Private Const IX_STATUS As Long = 19
Private Const IX_WO As Long = 20
Private Const IX_COST As Long = 21

Private Const STATUS_WARNING As String = "Warning"
Private Const STATUS_HEALTHY As String = "Healthy"

'------------------------------------------------------------------------------
' Main entry point
'------------------------------------------------------------------------------
Public Sub CleanAndSummarize()
    Dim startTime As Double
    startTime = Timer                                   ' benefit measurement: start

    Dim folderPath As String
    folderPath = GetSampleDataFolder()
    If folderPath = "" Then Exit Sub

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    Application.Calculation = xlCalculationManual

    Dim seen As Object: Set seen = CreateObject("Scripting.Dictionary")
    Dim cleanRows As Collection: Set cleanRows = New Collection

    Dim rowsRead As Long, dupRemoved As Long, missingDist As Long, missingCost As Long
    Dim statusFixed As Long, fileCount As Long

    ' Read every CSV in sample-data (eliminates Motion: no manual file opening)
    Dim fileName As String
    fileName = Dir(folderPath & "\*.csv")
    Do While fileName <> ""
        fileCount = fileCount + 1
        ProcessOneFile folderPath & "\" & fileName, seen, cleanRows, _
                       rowsRead, dupRemoved, missingDist, missingCost, statusFixed
        fileName = Dir
    Loop

    If fileCount = 0 Then
        Application.Calculation = xlCalculationAutomatic
        Application.DisplayAlerts = True
        Application.ScreenUpdating = True
        MsgBox "No .csv files found in:" & vbCrLf & folderPath, vbExclamation
        Exit Sub
    End If

    Dim totalWarnings As Long
    WriteCleanSheet cleanRows
    WriteSummarySheet cleanRows, rowsRead, dupRemoved, missingDist, missingCost, _
                      statusFixed, fileCount, totalWarnings

    Application.Calculation = xlCalculationAutomatic
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True

    Dim elapsed As Double
    elapsed = Timer - startTime                          ' benefit measurement: end

    ' Write the measured runtime back so the ROI model can reference it
    ThisWorkbook.Worksheets("Summary").Range("B9").Value = Round(elapsed, 3)

    MsgBox "Automation complete." & vbCrLf & vbCrLf & _
           "Files read              : " & fileCount & vbCrLf & _
           "Raw rows read           : " & rowsRead & vbCrLf & _
           "Duplicate rows removed  : " & dupRemoved & vbCrLf & _
           "Clean rows              : " & cleanRows.Count & vbCrLf & _
           "Status case normalized  : " & statusFixed & vbCrLf & _
           "Total WARNING readings  : " & totalWarnings & vbCrLf & _
           "Missing NearestDistance : " & missingDist & vbCrLf & _
           "Missing MaintenanceCost : " & missingCost & vbCrLf & vbCrLf & _
           "ELAPSED: " & Format(elapsed, "0.000") & " seconds" & vbCrLf & _
           "(Record this number in README.md)", _
           vbInformation, "CleanAndSummarize"
End Sub

'------------------------------------------------------------------------------
' Read one CSV, clean each row, de-duplicate, append to cleanRows
'------------------------------------------------------------------------------
Private Sub ProcessOneFile(ByVal filePath As String, ByRef seen As Object, _
                           ByRef cleanRows As Collection, _
                           ByRef rowsRead As Long, ByRef dupRemoved As Long, _
                           ByRef missingDist As Long, ByRef missingCost As Long, _
                           ByRef statusFixed As Long)
    Dim ff As Integer: ff = FreeFile
    Dim line As String
    Dim isHeader As Boolean: isHeader = True
    Dim parts() As String
    Dim exportDate As Date
    Dim okDate As Boolean
    Dim equipID As String, rawStatus As String, status As String
    Dim distTxt As String, costTxt As String
    Dim distVal As Variant, costVal As Variant
    Dim key As String
    Dim rec(0 To COL_COUNT - 1) As Variant
    Dim j As Long

    Open filePath For Input As #ff
    Do Until EOF(ff)
        Line Input #ff, line
        If isHeader Then
            isHeader = False                             ' skip header (may carry a UTF-8 BOM)
        ElseIf Len(Trim$(line)) > 0 Then
            rowsRead = rowsRead + 1
            parts = Split(line, DELIM)

            If UBound(parts) = COL_COUNT - 1 Then
                ' --- cleaning rules (eliminate Defects / Overprocessing) ---
                okDate = NormalizeDate(parts(IX_DATE), exportDate)
                equipID = UCase$(Trim$(parts(IX_EQUIP)))  ' trim spaces + unify case

                rawStatus = Trim$(parts(IX_STATUS))
                status = NormalizeStatus(rawStatus)

                distTxt = Trim$(parts(IX_DIST))
                costTxt = Trim$(parts(IX_COST))
                distVal = IIf(Len(distTxt) = 0, "", Val(distTxt))
                ' CleanNumber strips thousand separators
                costVal = IIf(Len(costTxt) = 0, "", CleanNumber(costTxt))

                If okDate Then
                    ' de-duplicate on date|equipment|cycle|timestamp|work order
                    key = Format$(exportDate, "yyyy-mm-dd") & "|" & equipID & "|" & _
                          Trim$(parts(IX_CYCLE)) & "|" & Trim$(parts(IX_TS)) & "|" & _
                          Trim$(parts(IX_WO))

                    If seen.Exists(key) Then
                        dupRemoved = dupRemoved + 1
                    Else
                        seen.Add key, 1

                        ' Count data-quality issues on kept rows only, so that
                        ' duplicates do not inflate the figures.
                        If status <> rawStatus Then statusFixed = statusFixed + 1
                        If distVal = "" Then missingDist = missingDist + 1
                        If costVal = "" Then missingCost = missingCost + 1

                        rec(IX_DATE) = exportDate
                        rec(IX_EQUIP) = equipID
                        rec(IX_CYCLE) = CLng(Val(parts(IX_CYCLE)))
                        rec(IX_TS) = Trim$(parts(IX_TS))
                        For j = IX_SENSOR_FIRST To IX_SENSOR_LAST
                            rec(j) = Val(Trim$(parts(j)))  ' Val is locale-independent
                        Next j
                        rec(IX_Z1) = Val(Trim$(parts(IX_Z1)))
                        rec(IX_Z2) = Val(Trim$(parts(IX_Z2)))
                        rec(IX_DIST) = distVal
                        rec(IX_STATUS) = status
                        rec(IX_WO) = Trim$(parts(IX_WO))
                        rec(IX_COST) = costVal
                        cleanRows.Add rec
                    End If
                End If
            End If
        End If
    Loop
    Close #ff
End Sub

'------------------------------------------------------------------------------
' Write the "CleanData" worksheet (all 22 cleaned columns)
'------------------------------------------------------------------------------
Private Sub WriteCleanSheet(ByRef cleanRows As Collection)
    Dim ws As Worksheet: Set ws = GetOrCreateSheet("CleanData")
    ws.Cells.Clear

    Dim hdr As Variant
    hdr = Array("ExportDate", "EquipmentID", "Cycle", "Timestamp", _
                "Sensor_2", "Sensor_3", "Sensor_4", "Sensor_7", "Sensor_8", "Sensor_9", _
                "Sensor_11", "Sensor_12", "Sensor_13", "Sensor_14", "Sensor_15", "Sensor_17", _
                "LatentZ1", "LatentZ2", "NearestDistance", "PredictedStatus", _
                "WorkOrder", "MaintenanceCost")
    ws.Range("A1").Resize(1, COL_COUNT).Value = hdr
    ws.Range("A1").Resize(1, COL_COUNT).Font.Bold = True

    If cleanRows.Count = 0 Then Exit Sub

    Dim data() As Variant
    ReDim data(1 To cleanRows.Count, 1 To COL_COUNT)

    Dim i As Long, j As Long
    Dim rec As Variant
    For i = 1 To cleanRows.Count
        rec = cleanRows(i)
        For j = 0 To COL_COUNT - 1
            data(i, j + 1) = rec(j)
        Next j
    Next i

    ws.Range("A2").Resize(cleanRows.Count, COL_COUNT).Value = data
    ws.Columns("A").NumberFormat = "yyyy-mm-dd"
    ws.Columns("V").NumberFormat = "#,##0.00"
    ' No AutoFit on the data body: on 13k+ rows it costs seconds and would
    ' distort the runtime measurement, which is about automation, not cosmetics.
    ws.Rows(1).AutoFit
End Sub

'------------------------------------------------------------------------------
' Write the "Summary" worksheet: per-equipment aggregation (replaces manual pivot)
'------------------------------------------------------------------------------
Private Sub WriteSummarySheet(ByRef cleanRows As Collection, _
                              ByVal rowsRead As Long, ByVal dupRemoved As Long, _
                              ByVal missingDist As Long, ByVal missingCost As Long, _
                              ByVal statusFixed As Long, ByVal fileCount As Long, _
                              ByRef totalWarnings As Long)
    Dim ws As Worksheet: Set ws = GetOrCreateSheet("Summary")
    ws.Cells.Clear

    ' --- Block 2 first: aggregate so we can report the warning total up top ---
    Dim agg As Object: Set agg = CreateObject("Scripting.Dictionary")

    Dim i As Long
    Dim rec As Variant, a As Variant
    Dim eid As String
    For i = 1 To cleanRows.Count
        rec = cleanRows(i)
        eid = rec(IX_EQUIP)

        If Not agg.Exists(eid) Then
            ' 0:rows  1:warnings  2:dist sum  3:dist count  4:cost sum
            agg.Add eid, Array(0#, 0#, 0#, 0#, 0#)
        End If

        a = agg(eid)
        a(0) = a(0) + 1
        If rec(IX_STATUS) = STATUS_WARNING Then a(1) = a(1) + 1
        If rec(IX_DIST) <> "" Then
            a(2) = a(2) + rec(IX_DIST)
            a(3) = a(3) + 1
        End If
        If rec(IX_COST) <> "" Then a(4) = a(4) + rec(IX_COST)
        agg(eid) = a
    Next i

    totalWarnings = 0
    Dim keys As Variant: keys = agg.keys
    Dim k As Long
    For k = LBound(keys) To UBound(keys)
        totalWarnings = totalWarnings + agg(keys(k))(1)
    Next k

    ' --- Block 1: run log (measured values consumed by the ROI model) ---
    ws.Range("A1").Value = "Automation run log (measured)"
    ws.Range("A1").Font.Bold = True
    ws.Range("A2").Value = "Files read":               ws.Range("B2").Value = fileCount
    ws.Range("A3").Value = "Raw rows read":            ws.Range("B3").Value = rowsRead
    ws.Range("A4").Value = "Duplicate rows removed":   ws.Range("B4").Value = dupRemoved
    ws.Range("A5").Value = "Clean rows":               ws.Range("B5").Value = cleanRows.Count
    ws.Range("A6").Value = "Status case normalized":   ws.Range("B6").Value = statusFixed
    ws.Range("A7").Value = "Total WARNING readings":   ws.Range("B7").Value = totalWarnings
    ws.Range("A8").Value = "Missing NearestDistance":  ws.Range("B8").Value = missingDist
    ws.Range("A9").Value = "Elapsed seconds":          ws.Range("B9").Value = 0  ' filled by caller
    ws.Range("A10").Value = "Missing MaintenanceCost": ws.Range("B10").Value = missingCost

    ' --- Block 2 output: sorted per-equipment table ---
    SortStrings keys

    Dim r As Long: r = 13
    ws.Cells(r - 1, 1).Value = "Per-equipment summary"
    ws.Cells(r - 1, 1).Font.Bold = True
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Value = _
        Array("EquipmentID", "Readings", "Warnings", "Warning Rate", _
              "Avg NearestDistance", "Total Cost")
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Font.Bold = True

    Dim firstDataRow As Long: firstDataRow = r + 1
    Dim v As Variant
    For k = LBound(keys) To UBound(keys)
        v = agg(keys(k))
        r = r + 1
        ws.Cells(r, 1).Value = keys(k)
        ws.Cells(r, 2).Value = v(0)
        ws.Cells(r, 3).Value = v(1)
        ws.Cells(r, 4).Value = IIf(v(0) > 0, v(1) / v(0), "")
        ws.Cells(r, 5).Value = IIf(v(3) > 0, v(2) / v(3), "")
        ws.Cells(r, 6).Value = v(4)
    Next k

    If r >= firstDataRow Then
        ws.Range(ws.Cells(firstDataRow, 4), ws.Cells(r, 4)).NumberFormat = "0.0%"
        ws.Range(ws.Cells(firstDataRow, 5), ws.Cells(r, 5)).NumberFormat = "0.000000"
        ws.Range(ws.Cells(firstDataRow, 6), ws.Cells(r, 6)).NumberFormat = "#,##0.00"
    End If
    ws.Columns("A:F").AutoFit
    ws.Activate
End Sub

'==============================================================================
' Helper functions
'==============================================================================

' Unify PredictedStatus casing. "warning"/"WARNING" -> "Warning".
' Without this, a pivot table silently splits the KPI into several categories.
Private Function NormalizeStatus(ByVal s As String) As String
    Select Case UCase$(Trim$(s))
        Case "WARNING": NormalizeStatus = STATUS_WARNING
        Case "HEALTHY": NormalizeStatus = STATUS_HEALTHY
        Case Else:      NormalizeStatus = Trim$(s)
    End Select
End Function

' Simple insertion sort for a 0-based Variant array of strings
Private Sub SortStrings(ByRef arr As Variant)
    Dim i As Long, j As Long
    Dim tmp As Variant
    For i = LBound(arr) + 1 To UBound(arr)
        tmp = arr(i)
        j = i - 1
        Do While j >= LBound(arr)
            If arr(j) <= tmp Then Exit Do
            arr(j + 1) = arr(j)
            j = j - 1
        Loop
        arr(j + 1) = tmp
    Next i
End Sub

' Parse the three mixed date formats: yyyy/mm/dd, yyyy-mm-dd, dd-Mon-yyyy
Private Function NormalizeDate(ByVal s As String, ByRef outDate As Date) As Boolean
    s = Trim$(s)
    Dim p() As String

    If InStr(s, "/") > 0 Then
        p = Split(s, "/")
        If UBound(p) = 2 Then
            outDate = DateSerial(CLng(p(0)), CLng(p(1)), CLng(p(2)))
            NormalizeDate = True
        End If
        Exit Function
    End If

    If InStr(s, "-") > 0 Then
        p = Split(s, "-")
        If UBound(p) = 2 Then
            If Len(p(0)) = 4 Then                       ' yyyy-mm-dd
                outDate = DateSerial(CLng(p(0)), CLng(p(1)), CLng(p(2)))
                NormalizeDate = True
            Else                                        ' dd-Mon-yyyy
                Dim m As Long: m = MonthFromAbbrev(p(1))
                If m > 0 Then
                    outDate = DateSerial(CLng(p(2)), m, CLng(p(0)))
                    NormalizeDate = True
                End If
            End If
        End If
    End If
End Function

' Month abbreviation -> month number (does not depend on system locale)
Private Function MonthFromAbbrev(ByVal mon As String) As Long
    Dim names As Variant
    names = Array("JAN", "FEB", "MAR", "APR", "MAY", "JUN", _
                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    Dim i As Long
    For i = LBound(names) To UBound(names)
        If UCase$(Trim$(mon)) = names(i) Then
            MonthFromAbbrev = i + 1
            Exit Function
        End If
    Next i
End Function

' Strip thousand separators, then convert to a number
Private Function CleanNumber(ByVal s As String) As Double
    CleanNumber = Val(Replace(Trim$(s), ",", ""))
End Function

' Locate the folder of SAP_EXPORT_*.csv to process.
' The data ships in two scenarios (see README): sample-data\lifecycle (default)
' and sample-data\snapshot. Ask the user which to run; fall back to a picker.
Private Function GetSampleDataFolder() As String
    Dim lifecycle As String, snapshot As String
    lifecycle = ThisWorkbook.Path & "\sample-data\lifecycle"
    snapshot = ThisWorkbook.Path & "\sample-data\snapshot"

    If Len(Dir(lifecycle, vbDirectory)) > 0 Then
        Dim ans As VbMsgBoxResult
        ans = MsgBox("Process the LIFECYCLE dataset (~13,750 rows)?" & vbCrLf & vbCrLf & _
                     "Yes = lifecycle   |   No = snapshot (~315 rows)   |   Cancel = pick a folder", _
                     vbYesNoCancel + vbQuestion, "Choose dataset")
        If ans = vbYes Then
            GetSampleDataFolder = lifecycle
            Exit Function
        ElseIf ans = vbNo And Len(Dir(snapshot, vbDirectory)) > 0 Then
            GetSampleDataFolder = snapshot
            Exit Function
        ElseIf ans = vbCancel Then
            ' fall through to picker
        Else
            GetSampleDataFolder = snapshot   ' No, but snapshot missing -> try anyway
            Exit Function
        End If
    End If

    With Application.FileDialog(msoFileDialogFolderPicker)
        .Title = "Select a folder containing SAP_EXPORT_*.csv"
        If .Show = -1 Then GetSampleDataFolder = .SelectedItems(1)
    End With
End Function

' Get a worksheet by name, creating it if needed
Private Function GetOrCreateSheet(ByVal nm As String) As Worksheet
    On Error Resume Next
    Set GetOrCreateSheet = ThisWorkbook.Worksheets(nm)
    On Error GoTo 0
    If GetOrCreateSheet Is Nothing Then
        Set GetOrCreateSheet = ThisWorkbook.Worksheets.Add( _
            After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
        GetOrCreateSheet.Name = nm
    End If
End Function
