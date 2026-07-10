Attribute VB_Name = "CleanAndSummarize"
'==============================================================================
' 模組：CleanAndSummarize
' 用途：取代維運工程師「手動下載 SAP 匯出檔 → Excel 人工清理 → 人工彙整」的作業。
'
' 對應 ASML JD：
'   "use macro to replace manual download from SAP, manual summary in excel"
'
' Lean 對應（消除的浪費）：
'   Motion         → 免去反覆匯入、複製貼上、切換視窗
'   Overprocessing → 清理與彙整規則標準化，不再每天重做
'   Defects        → 消除人工修正髒資料造成的錯誤
'
' 效益量測：本巨集以 Timer 記錄執行秒數，供 06-lean-lss/roi-validation.xlsx 使用（實測值）。
'
' 使用方式：
'   1. 將本檔匯入 Excel VBA 編輯器（Alt+F11 → 檔案 → 匯入檔案）
'   2. 活頁簿另存於 02-automation-vba\ 資料夾下（巨集會自動尋找 sample-data 子資料夾）
'   3. 執行 CleanAndSummarize（Alt+F8）
'==============================================================================
Option Explicit

Private Const DELIM As String = ";"     ' SAP 匯出常用分號分隔（千分位逗號才不會破壞欄位）
Private Const COL_COUNT As Long = 12

'------------------------------------------------------------------------------
' 主程序
'------------------------------------------------------------------------------
Public Sub CleanAndSummarize()
    Dim startTime As Double
    startTime = Timer                                   ' ← 效益量測起點

    Dim folderPath As String
    folderPath = GetSampleDataFolder()
    If folderPath = "" Then Exit Sub

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    Dim seen As Object: Set seen = CreateObject("Scripting.Dictionary")
    Dim cleanRows As Collection: Set cleanRows = New Collection

    Dim rowsRead As Long, dupRemoved As Long, missingHealth As Long, missingCost As Long
    Dim fileCount As Long

    '--- 逐一讀取 sample-data 內所有 CSV（消除 Motion：不需手動一個個開啟）---
    Dim fileName As String
    fileName = Dir(folderPath & "\*.csv")
    Do While fileName <> ""
        fileCount = fileCount + 1
        ProcessOneFile folderPath & "\" & fileName, seen, cleanRows, _
                       rowsRead, dupRemoved, missingHealth, missingCost
        fileName = Dir
    Loop

    If fileCount = 0 Then
        Application.ScreenUpdating = True
        MsgBox "在下列資料夾找不到任何 .csv：" & vbCrLf & folderPath, vbExclamation
        Exit Sub
    End If

    WriteCleanSheet cleanRows
    WriteSummarySheet cleanRows, rowsRead, dupRemoved, missingHealth, missingCost, fileCount

    Application.DisplayAlerts = True
    Application.ScreenUpdating = True

    Dim elapsed As Double
    elapsed = Timer - startTime                          ' ← 效益量測終點

    ' 把實測秒數寫進 Summary 供 ROI 表引用
    With ThisWorkbook.Worksheets("Summary")
        .Range("B8").Value = Round(elapsed, 3)
    End With

    MsgBox "自動化完成！" & vbCrLf & vbCrLf & _
           "讀取檔案數：" & fileCount & vbCrLf & _
           "讀入原始列數：" & rowsRead & vbCrLf & _
           "移除重複列：" & dupRemoved & vbCrLf & _
           "清理後列數：" & cleanRows.Count & vbCrLf & _
           "HealthScore 缺值：" & missingHealth & vbCrLf & _
           "MaintenanceCost 缺值：" & missingCost & vbCrLf & vbCrLf & _
           "【執行耗時：" & Format(elapsed, "0.000") & " 秒】" & vbCrLf & _
           "（此數字請填入 README 的『自動流程』欄位）", _
           vbInformation, "CleanAndSummarize"
End Sub

'------------------------------------------------------------------------------
' 讀取單一 CSV，清理每一列，去重後存入 cleanRows
'------------------------------------------------------------------------------
Private Sub ProcessOneFile(ByVal filePath As String, ByRef seen As Object, _
                           ByRef cleanRows As Collection, _
                           ByRef rowsRead As Long, ByRef dupRemoved As Long, _
                           ByRef missingHealth As Long, ByRef missingCost As Long)
    Dim ff As Integer: ff = FreeFile
    Dim line As String
    Dim isHeader As Boolean: isHeader = True

    Open filePath For Input As #ff
    Do Until EOF(ff)
        Line Input #ff, line
        If isHeader Then
            isHeader = False                             ' 略過標題列（含 UTF-8 BOM）
        ElseIf Len(Trim$(line)) > 0 Then
            rowsRead = rowsRead + 1

            Dim parts() As String
            parts = Split(line, DELIM)
            If UBound(parts) = COL_COUNT - 1 Then

                '--- 清理規則（消除 Defects / Overprocessing）---
                Dim exportDate As Date, okDate As Boolean
                okDate = NormalizeDate(parts(0), exportDate)

                Dim equipID As String
                equipID = UCase$(Trim$(parts(1)))        ' 去前後空白 + 統一大寫

                Dim healthTxt As String: healthTxt = Trim$(parts(8))
                Dim costTxt As String:   costTxt = Trim$(parts(11))

                Dim healthVal As Variant, costVal As Variant
                If Len(healthTxt) = 0 Then
                    healthVal = "": missingHealth = missingHealth + 1
                Else
                    healthVal = CDbl(healthTxt)
                End If

                If Len(costTxt) = 0 Then
                    costVal = "": missingCost = missingCost + 1
                Else
                    costVal = CleanNumber(costTxt)       ' 去千分位逗號 → 數值
                End If

                If okDate Then
                    '--- 去重：以「日期|機台|時戳|工單」為鍵（消除重複列造成的重複計數）---
                    Dim key As String
                    key = Format$(exportDate, "yyyy-mm-dd") & "|" & equipID & "|" & _
                          Trim$(parts(2)) & "|" & Trim$(parts(10))

                    If seen.Exists(key) Then
                        dupRemoved = dupRemoved + 1
                    Else
                        seen.Add key, 1
                        Dim rec(0 To 6) As Variant
                        rec(0) = exportDate
                        rec(1) = equipID
                        rec(2) = Trim$(parts(2))          ' Timestamp
                        rec(3) = healthVal
                        rec(4) = CLng(Val(Trim$(parts(9))))  ' AnomalyFlag
                        rec(5) = Trim$(parts(10))         ' WorkOrder
                        rec(6) = costVal
                        cleanRows.Add rec
                    End If
                End If
            End If
        End If
    Loop
    Close #ff
End Sub

'------------------------------------------------------------------------------
' 輸出「CleanData」工作表
'------------------------------------------------------------------------------
Private Sub WriteCleanSheet(ByRef cleanRows As Collection)
    Dim ws As Worksheet: Set ws = GetOrCreateSheet("CleanData")
    ws.Cells.Clear

    Dim hdr As Variant
    hdr = Array("ExportDate", "EquipmentID", "Timestamp", "HealthScore", _
                "AnomalyFlag", "WorkOrder", "MaintenanceCost")
    ws.Range("A1").Resize(1, 7).Value = hdr
    ws.Range("A1").Resize(1, 7).Font.Bold = True

    If cleanRows.Count = 0 Then Exit Sub

    Dim data() As Variant
    ReDim data(1 To cleanRows.Count, 1 To 7)

    Dim i As Long, j As Long
    For i = 1 To cleanRows.Count
        Dim rec As Variant: rec = cleanRows(i)
        For j = 0 To 6
            data(i, j + 1) = rec(j)
        Next j
    Next i

    ws.Range("A2").Resize(cleanRows.Count, 7).Value = data
    ws.Columns("A").NumberFormat = "yyyy-mm-dd"
    ws.Columns("G").NumberFormat = "#,##0.00"
    ws.Columns("A:G").AutoFit
End Sub

'------------------------------------------------------------------------------
' 輸出「Summary」工作表：依機台彙總（取代人工樞紐分析）
'------------------------------------------------------------------------------
Private Sub WriteSummarySheet(ByRef cleanRows As Collection, _
                              ByVal rowsRead As Long, ByVal dupRemoved As Long, _
                              ByVal missingHealth As Long, ByVal missingCost As Long, _
                              ByVal fileCount As Long)
    Dim ws As Worksheet: Set ws = GetOrCreateSheet("Summary")
    ws.Cells.Clear

    '--- 區塊一：執行紀錄（供 ROI 表引用的實測值）---
    ws.Range("A1").Value = "自動化執行紀錄（實測）"
    ws.Range("A1").Font.Bold = True
    ws.Range("A2").Value = "讀取檔案數":       ws.Range("B2").Value = fileCount
    ws.Range("A3").Value = "讀入原始列數":     ws.Range("B3").Value = rowsRead
    ws.Range("A4").Value = "移除重複列":       ws.Range("B4").Value = dupRemoved
    ws.Range("A5").Value = "清理後列數":       ws.Range("B5").Value = cleanRows.Count
    ws.Range("A6").Value = "HealthScore 缺值": ws.Range("B6").Value = missingHealth
    ws.Range("A7").Value = "MaintenanceCost 缺值": ws.Range("B7").Value = missingCost
    ws.Range("A8").Value = "執行耗時（秒）":   ws.Range("B8").Value = 0   ' 主程序回填

    '--- 區塊二：依機台彙總 ---
    Dim agg As Object: Set agg = CreateObject("Scripting.Dictionary")

    Dim i As Long
    For i = 1 To cleanRows.Count
        Dim rec As Variant: rec = cleanRows(i)
        Dim eid As String: eid = rec(1)

        If Not agg.Exists(eid) Then
            ' 0:列數 1:健康總和 2:健康有效筆數 3:異常數 4:成本總和
            agg.Add eid, Array(0#, 0#, 0#, 0#, 0#)
        End If

        Dim a As Variant: a = agg(eid)
        a(0) = a(0) + 1
        If rec(3) <> "" Then
            a(1) = a(1) + rec(3)
            a(2) = a(2) + 1
        End If
        a(3) = a(3) + rec(4)
        If rec(6) <> "" Then a(4) = a(4) + rec(6)
        agg(eid) = a
    Next i

    Dim r As Long: r = 11
    ws.Cells(r - 1, 1).Value = "依機台彙總報表"
    ws.Cells(r - 1, 1).Font.Bold = True
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Value = _
        Array("EquipmentID", "紀錄筆數", "平均健康分數", "異常次數", "異常率", "維護成本合計")
    ws.Range(ws.Cells(r, 1), ws.Cells(r, 6)).Font.Bold = True

    Dim keys As Variant: keys = agg.keys
    Dim k As Long
    For k = LBound(keys) To UBound(keys)
        Dim v As Variant: v = agg(keys(k))
        r = r + 1
        ws.Cells(r, 1).Value = keys(k)
        ws.Cells(r, 2).Value = v(0)
        ws.Cells(r, 3).Value = IIf(v(2) > 0, v(1) / v(2), "")
        ws.Cells(r, 4).Value = v(3)
        ws.Cells(r, 5).Value = IIf(v(0) > 0, v(3) / v(0), "")
        ws.Cells(r, 6).Value = v(4)
    Next k

    ws.Range(ws.Cells(12, 3), ws.Cells(r, 3)).NumberFormat = "0.000"
    ws.Range(ws.Cells(12, 5), ws.Cells(r, 5)).NumberFormat = "0.0%"
    ws.Range(ws.Cells(12, 6), ws.Cells(r, 6)).NumberFormat = "#,##0.00"
    ws.Columns("A:F").AutoFit
    ws.Activate
End Sub

'==============================================================================
' 工具函式
'==============================================================================

'--- 解析三種混用的日期格式：yyyy/mm/dd、yyyy-mm-dd、dd-Mon-yyyy ---
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

'--- 英文月份縮寫 → 月份數字（不依賴系統地區設定）---
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

'--- 去除千分位逗號後轉為數值 ---
Private Function CleanNumber(ByVal s As String) As Double
    CleanNumber = CDbl(Replace(Trim$(s), ",", ""))
End Function

'--- 取得 sample-data 資料夾；找不到就讓使用者選 ---
Private Function GetSampleDataFolder() As String
    Dim guess As String
    guess = ThisWorkbook.Path & "\sample-data"
    If Len(Dir(guess, vbDirectory)) > 0 Then
        GetSampleDataFolder = guess
        Exit Function
    End If

    With Application.FileDialog(msoFileDialogFolderPicker)
        .Title = "請選擇存放 SAP_EXPORT_*.csv 的 sample-data 資料夾"
        If .Show = -1 Then GetSampleDataFolder = .SelectedItems(1)
    End With
End Function

'--- 取得或建立工作表 ---
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
