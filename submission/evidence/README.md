# Evidence cá nhân

Đặt ảnh hoặc output text dùng để chấm vào thư mục này. Danh sách đầy đủ xem tại [docs/SUBMISSION.md](../../docs/SUBMISSION.md).

Tên file gợi ý:

```text
01-pytest.png
02-log-validator.png
03-dashboard-validator.png
04-structured-log.png
05-pii-redaction.png
06-trace-list.png
07-trace-waterfall.png
08-trace-metadata.png
09-prompt-versions.png
10-prompt-rollback.png
11-dashboard-overview.png
12-incident-metric.png (+ `.txt` challenge data)
13-incident-log.png (+ `.txt` challenge log)
14-incident-trace.png (+ `.txt` challenge trace)
```

Có thể dùng `.txt` cho output của tests/validators. Có thể tách dashboard thành nhiều ảnh nếu một ảnh không đọc rõ.

Ảnh `04`, `05`, `13` lấy từ terminal hoặc `data/logs.jsonl`. Ảnh `06`–`10`, `14` lấy từ project Langfuse cá nhân `day13-k4-l3a-<MSSV>` và nên nhìn thấy tên project. Không mở/chụp trang API Keys.

Challenge chính thức đã chạy ngày 2026-09-29. Các PNG `12`–`14` là bản sao ảnh bổ trợ chụp trước challenge, không phải ảnh của incident chính thức. Các file `12-incident-metric.txt`, `13-incident-log.txt`, `14-incident-trace.txt` lưu số liệu/trích xuất khớp với challenge. File challenge chính thức nằm ở `config/challenge.json` local và bị `.gitignore`; không commit hoặc chia sẻ file đó.

Từ `submission/REPORT.md`, dẫn ảnh bằng đường dẫn tương đối:

```markdown
![Trace waterfall](evidence/07-trace-waterfall.png)
```

Không commit secret, API key, PII thô hoặc evidence của học viên/lớp khác.
