Attribute VB_Name = "CleanAndSummarize"
'==============================================================================
' Module : CleanAndSummarize
' Purpose: Replace the manual workflow of "download SAP export -> clean in Excel
'          -> summarize by hand" for the equipment health reporting process.
'
' ASML JD mapping:
'   "use macro to replace manual download from SAP, manual summary in excel"
'
' Lean waste eliminated:
'   Motion         -> no repeated importing, copy-pasting, window switching
'   Overprocessing -> cleaning and summary rules standardized, not redone daily
'   Defects        -> removes human error when fixing dirty data by hand
'                     (e.g. forgetting to TRIM equipment IDs splits one machine
'                      into two rows in a pivot table)
'
' Data source:
'   sample-data/SAP_EXPORT_*.csv, derived from the real NASA CMAPSS FD001
'   dataset (100 engines, 12 key sensors, HealthScore from true RUL).
'   See README.md for which fields are real and which are simulated.
'
' Input layout (semicolon separated, 20 columns, 0-based index):
'   00 ExportDate   01 EquipmentID  02 Cycle       03 Timestamp
'   04..15 Sensor_2,3,4,7,8,9,11,12,13,14,15,17
'   16 HealthScore  17 AnomalyFlag  18 WorkOrder   19 MaintenanceCost
'
' Benefit measurement:
'   This macro records its own runtime with Timer and writes it to Summary!B8.
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
Private Const COL_COUNT As Long = 20

' 0-based column indexes into the split line
Private Const IX_DATE As Long = 0
Private Const IX_EQUIP As Long = 1
Private Const IX_CYCLE As Long = 2
Private Const IX_TS As Long = 3
Private Const IX_SENSOR_FIRST As Long = 4
Private Const IX_SENSOR_LAST As Long = 15
Private Const IX_HEALTH As Long = 16
Private Const IX_ANOMALY As Long = 17
Private Const IX_WO As Long = 18
Private Const IX_COST As Long = 19

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

    Dim rowsRead As Long, dupRemoved As Long, missingHealth As Long, missingCost As Long
    Dim fileCount As Long

    ' Read every CSV in sample-data (eliminates Motion: no manual file opening)
    Dim fileName As String
    fileName = Dir(folderPath & "\*.csv")
    Do While fileName <> ""
        fileCount = fileCount + 1
        ProcessOneFile folderPath & "\" & fileName, seen, cleanRows, _
                       rowsRead, dupRemoved, missingHealth, missingCost
        fileName = Dir
    Loop

    If fileCount = 0 Then
        Application.Calculation = xlCalculationAutomatic
        Application.DisplayAlerts = True
        Application.ScreenUpdating = True
        MsgBox "No .csv files found in:" & vbCrLf & folderPath, vbExclamation
        Exit Sub
    End If

    WriteCleanSheet cleanRows
    WriteSummarySheet cleanRows, rowsRead, dupRemoved, missingHealth, missingCost, fileCount

    Application.Calculation = xlCalculationAutomatic
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True

    Dim elapsed As Double
    elapsed = Timer - startTime                          ' benefit measurement: end

    ' Write the measured runtime back so the ROI model can reference it
    ThisWorkbook.Worksheets("Summary").Range("B8").Value = Round(elapsed, 3)

    MsgBox "Automation complete." & vbCrLf & vbCrLf & _
           "Files read             : " & fileCount & vbCrLf & _
           "Raw rows read          : " & rowsRead & vbCrLf & _
           "Duplicate rows removed : " & dupRemoved & vbCrLf & _
           "Clean rows             : " & cleanRows.Count & vbCrLf & _
           "Missing HealthScore    : " & missingHealth & vbCrLf & _
           "Missing MaintenanceCost: " & missingCost & vbCrLf & vbCrLf & _
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
                           ByRef missingHealth As Long, ByRef missingCost As Long)
    Dim ff As Integer: ff = FreeFile
    Dim line As String
    Dim isHeader As Boolean: isHeader = True
    Dim parts() As String
    Dim exportDate As Date
    Dim okDate As Boolean
    Dim equipID As String
    Dim healthTxt As String, costTxt As String
    Dim healthVal As Variant, costVal As Variant
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

                healthTxt = Trim$(parts(IX_HEALTH))
                costTxt = Trim$(parts(IX_COST))

                If Len(healthTxt) = 0 Then
                    healthVal = ""
                    missingHealth = missingHealth + 1
                Else
                    healthVal = Val(healthTxt)
                End If

                If Len(costTxt) = 0 Then
                    costVal = ""
                    missingCost = missingCost + 1
                Else
                    costVal = CleanNumber(costTxt)       ' strip thousand separators
                End If

                If okDate Then
                    ' de-duplicate on date|equipment|cycle|timestamp|work order
                    key = Format$(exportDate, "yyyy-mm-dd") & "|" & equipID & "|" & _
                          Trim$(parts(IX_CYCLE)) & "|" & Trim$(parts(IX_TS)) & "|" & _
                          Trim$(parts(IX_WO))

                    If seen.Exists(key) Then
                        dupRemoved = dupRemoved + 1
                    Else
                        seen.Add key, 1
                        rec(IX_DATE) = exportDate
                        rec(IX_EQUIP) = equipID
                        rec(IX_CYCLE) = CLng(Val(parts(IX_CYCLE)))
                        rec(IX_TS) = Trim$(parts(IX_TS))
                        For j = IX_SENSOR_FIRST To IX_SENSOR_LAST
                            rec(j) = Val(Trim$(parts(j)))  ' Val is locale-independent
                        Next j
                        rec(IX_HEALTH) = healthVal
                        rec(IX_ANOMALY) = CLng(Val(parts(IX_ANOMALY)))
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
' Write the "CleanData" worksheet (all 20 cleaned columns)
'------------------------------------------------------------------------------
Private Sub WriteCleanSheet(ByRef cleanRows As Collection)
    Dim ws As Worksheet: Set ws = GetOrCreateSheet("CleanData")
    ws.Cells.Clear

    Dim hdr As Variant
    hdr = Array("ExportDate", "EquipmentID", "Cycle", "Timestamp", _
                "Sensor_2", "Sensor_3", "Sensor_4", "Sensor_7", "Sensor_8", "Sensor_9", _
                "Sensor_11", "Sensor_12", "Sensor_13", "Sensor_14", "Sensor_15", "Sensor_17", _
                "HealthScore", "AnomalyFlag", "WorkOrder", "MaintenanceCost")
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
    ws.Columns("T").NumberFormat = "#,##0.00"
    ' No AutoFit here: on 20k+ rows it costs seconds and would distort the
    ' runtime measurement, which is about automation, not cosmetics.
    ws.Rows(1).AutoFit
End Sub

'------------------------------------------------------------------------------
' Write the "Summary" worksheet: per-equipment aggregation (replaces manual pivot)
'------------------------------------------------------------------------------
Private Sub WriteSummarySheet(ByRef cleanRows As Collection, _
                              ByVal rowsRead As Long, ByVal dupRemoved As Long, _
                              ByVal missingHealth As Long, ByVal missingCost As Long, _
                              ByVal fileCount As Long)
    Dim ws As Worksheet: Set ws = GetOrCreateSheet("Summary")
    ws.Cells.Clear

    ' --- Block 1: run log (measured values consumed by the ROI model) ---
    ws.Range("A1").Value = "Automation run log (measured)"
    ws.Range("A1").Font.Bold = True
    ws.Range("A2").Value = "Files read":              ws.Range("B2").Value = fileCount
    ws.Range("A3").Value = "Raw rows read":           ws.Range("B3").Value = rowsRead
    ws.Range("A4").Value = "Duplicate rows removed":  ws.Range("B4").Value = dupRemoved
    ws.Range("A5").Value = "Clean rows":              ws.Range("B5").Value = cleanRows.Count
    ws.Range("A6").Value = "Missing HealthScore":     ws.Range("B6").Value = missingHealth
    ws.Range("A7").Value = "Missing MaintenanceCost": ws.Range("B7").Value = missingCost
    ws.Range("A8").Value = "Elapsed seconds":         ws.Range("B8").Value = 0  ' filled by caller

    ' --- Block 2: per-equipment aggregation ---
    Dim agg As Object: Set agg = CreateObject("Scripting.Dictionary")

    Dim i As Long
    Dim rec As Variant, a As Variant
    Dim eid As String
    For i = 1 To cleanRows.Count
        rec = cleanRows(i)
        eid = rec(IX_EQUIP)

        If Not agg.Exists(eid) Then
            ' 0:rows  1:health sum  2:health count  3:anomalies  4:cost sum
            agg.Add eid, Array(0#, 0#, 0#, 0#, 0#)
        End If

        a = agg(eid)
        a(0) = a(0) + 1
        If rec(IX_HEALTH) <> "" Then
            a(1) = a(1) + rec(IX_HEALTH)
            a(2) = a(2) + 1
        End If
        a(3) = a(3) + rec(IX_ANOMALY)
        If rec(IX_COST) <> "" Then a(4) = a(4) + rec(IX_COST)
        agg(eid) = a
    Next i

    Dim r As Long: r = 11
    ws.Cells(r - 1, 1).Value = "Per-equipment summary"
    ws.Cells(r - 1, 1).Font.Bold = True
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Value = _
        Array("EquipmentID", "Records", "Avg HealthScore", "Anomalies", "Anomaly Rate", "Total Cost")
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Font.Bold = True

    ' Sort equipment IDs so the report is stable and readable
    Dim keys As Variant: keys = agg.keys
    SortStrings keys

    Dim k As Long
    Dim v As Variant
    For k = LBound(keys) To UBound(keys)
        v = agg(keys(k))
        r = r + 1
        ws.Cells(r, 1).Value = keys(k)
        ws.Cells(r, 2).Value = v(0)
        ws.Cells(r, 3).Value = IIf(v(2) > 0, v(1) / v(2), "")
        ws.Cells(r, 4).Value = v(3)
        ws.Cells(r, 5).Value = IIf(v(0) > 0, v(3) / v(0), "")
        ws.Cells(r, 6).Value = v(4)
    Next k

    If r >= 12 Then
        ws.Range(ws.Cells(12, 3), ws.Cells(r, 3)).NumberFormat = "0.000"
        ws.Range(ws.Cells(12, 5), ws.Cells(r, 5)).NumberFormat = "0.0%"
        ws.Range(ws.Cells(12, 6), ws.Cells(r, 6)).NumberFormat = "#,##0.00"
    End If
    ws.Columns("A:F").AutoFit
    ws.Activate
End Sub

'==============================================================================
' Helper functions
'==============================================================================

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

' Locate the sample-data folder; fall back to a folder picker
Private Function GetSampleDataFolder() As String
    Dim guess As String
    guess = ThisWorkbook.Path & "\sample-data"
    If Len(Dir(guess, vbDirectory)) > 0 Then
        GetSampleDataFolder = guess
        Exit Function
    End If

    With Application.FileDialog(msoFileDialogFolderPicker)
        .Title = "Select the sample-data folder containing SAP_EXPORT_*.csv"
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
