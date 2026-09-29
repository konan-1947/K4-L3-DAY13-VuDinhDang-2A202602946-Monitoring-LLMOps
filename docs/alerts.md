# Alert và runbook Day 13

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.
Định nghĩa máy đọc được nằm ở [`../config/alert_rules.yaml`](../config/alert_rules.yaml); ba alert dưới đây khớp
1–1 với file đó theo thứ tự `high_p95_latency`, `high_error_rate_and_retrieval_failure`, `cost_budget_burn`.

Nguyên tắc chọn `duration`:

- `10m` với `window: 5m` để loại spike ngắn ( ví dụ lúc deploy) nhưng vẫn bắt sự cố kéo dài;
- `30m` với `window: 1d` vì cost tích luỹ theo ngày, báo sớm không giúp ngăn ngừa;
- `for_zero_traffic: false` chỉ dùng khi điều kiện cần mẫu số (ví dụ error rate) — không có traffic thì
  không báo để tránh alert giả.

Kênh thông báo chung của cả ba alert: Slack `#day13-alerts`. Owner: `day13-oncall`.

## Alert 1

- Tên: `high_p95_latency`
- Severity: critical
- Duration: `10m` duy trì liên tục trên `window: 5m`
- Kênh thông báo: Slack `#day13-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (P95 latency > 2000 ms), panel `latency` của dashboard
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 2000` giữ liên tục 10 phút
- Ảnh hưởng tới người dùng: người dùng chờ hơn 2 giây cho mỗi câu trả lời, tỷ lệ bỏ phiên tăng
- Vì sao chọn 2000 ms: baseline đo được P95 = 151 ms; khi bật incident practice `rag_slow`,
  P95 = 2651 ms. Ngưỡng 3000 ms của starter sẽ không bắt được sự cố này, nên đã hạ xuống 2000 ms
  (xem `config/slo.yaml` và `config/dashboard.yaml`).
- Ba bước kiểm tra đầu tiên:
  1. Mở panel `latency`, so P95 với P50 để biết đây là tail latency hay toàn hệ thống chậm.
  2. Lọc `data/logs.jsonl` theo khoảng thời gian alert, lấy vài `correlation_id` của `response_sent` có `latency_ms` cao.
  3. Mở trace có cùng `correlation_id` và so thời lượng span `retrieval` với `llm-generation`.
- Mitigation tạm thời: nếu span `retrieval` chiếm phần lớn thời gian thì giảm `top_k`/timeout của vector store
  hoặc phục vụ cache kết quả truy hồi; nếu span `llm-generation` chiếm phần lớn thì hạ `max_tokens`, chuyển sang
  model rẻ hơn hoặc rollback prompt về bản ngắn hơn. Nếu chỉ là traffic đột biến thì giữ nguyên và theo dõi.
- Owner: `day13-oncall`
- Phòng ngừa: thêm alert burn-rate theo SLO và theo dõi p95 riêng theo từng bước (retrieval vs generation) để
  khoanh vùng nhanh hơn ở lần sau.

## Alert 2

- Tên: `high_error_rate_and_retrieval_failure`
- Severity: critical
- Duration: `10m` duy trì liên tục trên `window: 5m`
- Kênh thông báo: Slack `#day13-alerts`
- SLI/SLO liên quan: guardrail `error_rate_pct_max: 2` và `retrieval_success_rate_pct_min: 90`, panel `errors`
- Điều kiện và thời gian duy trì: `error_rate_pct > 2 or tool_success_rate_pct < 90` giữ liên tục 10 phút
- Ảnh hưởng tới người dùng: request trả về lỗi hoặc câu trả lời không có ngữ cảnh vì bước truy hồi thất bại
- Ba bước kiểm tra đầu tiên:
  1. Xem breakdown `error_type` trên panel `errors` để biết lỗi tập trung ở nhóm nào.
  2. Lọc log `request_failed` lấy `correlation_id` rồi mở trace tương ứng, kiểm tra span `retrieval`
     có `level=ERROR`/`status_message` không.
  3. Đối chiếu `tool_success` trong log với `tool_success_rate_pct` để xác nhận lỗi đến từ vector store
     hay từ chính tầng API.
- Mitigation tạm thời: bật fallback trả lời bằng kiến thức chung khi retrieval lỗi (`POST /incidents/rag_slow/disable`
  chỉ dùng cho practice), hoặc hạ tải bằng cách giới hạn concurrency; nếu lỗi do deploy thì rollback bản
  deploy gần nhất trước khi debug sâu.
- Owner: `day13-oncall`
- Phòng ngừa: thêm timeout + retry có backoff cho vector store, và cảnh báo riêng khi `tool_success_rate_pct`
  giảm dù error rate API vẫn bằng 0.

## Alert 3

- Tên: `cost_budget_burn`
- Severity: warning
- Duration: `30m` trên `window: 1d`
- Kênh thông báo: Slack `#day13-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`, panel `cost` (kèm panel `tokens` để phân rã)
- Điều kiện và thời gian duy trì: `sum(response_sent.cost_usd) over 1d > 2.5` hoặc
  `cost_per_request > 2x cost_per_request_7d`, giữ 30 phút
- Ảnh hưởng tới người dùng: không hỏng tính năng nhưng độ dài câu trả lời tăng, chi phí vượt ngân sách và
  có nguy cơ độ trễ tăng theo vì context lớn hơn
- Ba bước kiểm tra đầu tiên:
  1. So panel `cost` với panel `tokens`: cost tăng do token tăng hay do traffic tăng.
  2. Nếu `tokens_out` tăng còn `tokens_in` không đổi thì nghi do prompt/câu trả lời dài: mở trace, đọc
     `usage_details` và `prompt_version` trên span `llm-generation`.
  3. Kiểm tra `prompt_version` trong trace có đúng label `production` dự kiến không (tránh tình huống
     rollback chưa được áp dụng).
- Mitigation tạm thời: rollback label `production` về prompt ngắn hơn, giảm `max_tokens`, chuyển traffic sang
  model rẻ hơn; nếu do một feature cụ thể sinh cost thì tắt feature đó qua cấu hình thay vì sửa code runtime.
- Owner: `day13-oncall`
- Phòng ngừa: theo dõi `cost_per_request` theo feature, đặt budget theo ngày và alert khi burn-rate vượt 2x
  mức trung bình 7 ngày.

## Điều kiện ứng viên chưa chọn

Panel `quality` (mean `quality_score`) hiện chỉ nằm trong guardrail, chưa có alert riêng vì quality proxy của lab
là heuristic và chưa đủ tin cậy để bật cảnh báo tự động. Nếu workload thật thay heuristic, nên thêm alert
`mean(quality_score) < 0.75` với `duration: 1h` và cùng owner.
