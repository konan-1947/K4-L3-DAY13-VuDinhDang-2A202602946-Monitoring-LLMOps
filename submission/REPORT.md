# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.
>
> Các kết quả dưới đây được lấy từ log ứng dụng, API Langfuse và validators chạy ngày 2026-09-29.
> File challenge chính thức được giữ local và nằm trong `.gitignore`; không commit file đó.

## 1. Thông tin học viên

- **Họ và tên:** Vu Dinh Dang
- **MSSV:** 2A202602946
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/konan-1947/K4-L3-DAY13-VuDinhDang-2A202602946-Monitoring-LLMOps
- **Commit SHA cuối dùng để chấm source/evidence:** `ad1a3b61c6b09148718f03c7cfd8dc46d9ca675a`
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602946`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.
Các evidence có trong thư mục được dẫn dưới đây. Incident API/log/trace trích xuất dạng `.txt`; ảnh UI incident vẫn cần chụp nếu giảng viên yêu cầu ảnh thay vì artifact text.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/09-prompt-versions.png` *(production hiện gắn v1 sau rollback; ảnh đang hiển thị tên project cũ)* |
| Dashboard runtime | `evidence/11-dashboard-overview.png`, `evidence/11-dashboard-details.png` *(ảnh bổ sung; dashboard chưa đủ sáu panel của lab)* |
| Incident metric | `evidence/12-incident-metric.txt`; ảnh dashboard bổ trợ `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.txt`; ảnh structured-log bổ trợ `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.txt`; ảnh trace bổ trợ `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

Baseline đo bằng `git worktree` tại commit `13b6066` (trước khi sửa CP1/CP2). Kết quả runtime hiện tại
được tạo trên project Langfuse Japan cấu hình trong `.env` (file bị Git ignore). Load test sinh 10 trace;
ban đầu prompt `day13-chat` chưa tồn tại nên chúng dùng `local-fallback`. Sau đó đã tạo prompt v1/v2 và
chạy thêm 5 trace kiểm chứng label baseline/candidate, promote, rollback và production v1 hiện tại. Challenge chính thức được chạy hai lượt (5 request/lượt) trong lúc xác minh output; incident đã được tắt sau workload.

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 — 20 dòng thiếu `correlation_id` + enrichment, 0 correlation ID duy nhất | 100/100 — lần kiểm tra sau challenge: 112 dòng log, 58 correlation ID, 0 PII leak | Vượt ngưỡng ≥80 |
| `validate_dashboard.py` | `HỢP LỆ: 6/6 panel` | `HỢP LỆ: 6/6 panel` | Giữ đủ 6 panel; chỉ đổi ngưỡng latency (xem mục 6) |
| `pytest` | 22 passed | 34 passed | +5 test child observation, +7 test config SLO/alert/runbook |
| Số traces hợp lệ | 0 | 25 (10 local-fallback + 5 prompt-managed + 10 challenge) | Challenge chạy 2 lượt, 5 request mỗi lượt; mỗi trace có root, retrieval, generation |
| Số PII leak trong log | 0 | 0 | Scrub chạy ở processor, cộng thêm ở bước ghi file |
| Latency / TTFT | 150 ms / 50 ms baseline | Baseline 151 ms; challenge: 5/5 request chậm hơn 2000 ms, latency server-side 2652–7766 ms; span retrieval ~2501 ms | Ngưỡng challenge 2000 ms bắt được sự cố; request đầu bị queue khi concurrency=5 |
| Retrieval success rate | 100% khi bình thường; 0% khi bật `tool_fail` | 100% | Guardrail ≥ 90% |
| Error rate | 0% | 0% bình thường; 100% khi bật `tool_fail` | Guardrail ≤ 2% |
| Cost 10 request | 0.0189 USD | 0.0194 USD | `tokens_out` ngẫu nhiên nên có dao động nhỏ |
| Quality proxy (mean) | 0.88 | 0.88 | Heuristic, chưa dùng làm alert |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `app/middleware.py:resolve_correlation_id` nhận header
  `x-request-id` nếu khớp `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`, ngược lại sinh `req-<8-hex>` bằng `uuid4`.
  `CorrelationIdMiddleware` gọi `clear_contextvars()` trước **và sau** mỗi request để không rò context,
  bind `correlation_id` vào structlog contextvars, gắn vào `request.state.correlation_id`, rồi trả lại
  `x-request-id` và `x-response-time-ms` trong response header.
- **Các metadata được ghi vào structured log:** `app/main.py` bind `user_id_hash` (SHA-256 12 ký tự),
  `session_id`, `feature`, `model`, `env` **trước** dòng `request_received`; `response_sent` ghi thêm
  `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`,
  `tool_success`; `request_failed` ghi `error_type`. `user_id` thô không bao giờ được ghi.
- **Cách bảo đảm PII được scrub trước khi ghi:** `app/logging_config.py` đặt `scrub_event` (gọi
  `app/pii.py:scrub_value`, đệ quy toàn bộ dict/list/str trong event_dict) **trước** `JsonlFileProcessor`
  và `JSONRenderer`; `JsonlFileProcessor` còn scrub lần nữa chuỗi đã render trước khi append vào file.
- **Cách kiểm chứng kết quả:** `python scripts/validate_logs.py` → 0 PII leak; ví dụ thực tế trong
  `data/logs.jsonl`: `"message_preview": "What is your refund policy? My email is [REDACTED_EMAIL]"`.
  Patterns đã thêm: `passport_vn`, `address_vn` cùng các pattern sẵn có (email, phone Việt Nam, CCCD, thẻ).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** API Observations v2 của project cấu hình
  trong `.env` trả các root traces từ workload; mỗi trace có 3 observation. 10 trace đầu dùng local fallback
  trước khi prompt được tạo; 5 trace kế tiếp dùng prompt thật; challenge thêm 10 trace (5 request × 2 lượt).
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (`@observe`, `as_type=agent`,
  `capture_input=False`, `capture_output=False`); child `retrieval` (`as_type=retriever`, có `doc_count`,
  input/output đã scrub) và child `llm-generation` (`as_type=generation`, có `model`, `prompt` link,
  `usage_details` input/output/total, `cost_details` input/output, `ttft_ms`).
  Khi truy hồi lỗi, span `retrieval` được đánh dấu `level=ERROR` + `status_message`.
  Cả hai child được mở qua `app/tracing.py:child_observation` nên khi không có SDK/key hoặc client test
  không hỗ trợ API v4, ứng dụng vẫn chạy với no-op observation.
- **Cách nối trace với log:** `propagate_attributes(metadata={"correlation_id": ...})` ghi `correlation_id`
  vào metadata của trace; log dùng đúng giá trị đó. Lọc `correlation_id` trong `data/logs.jsonl` sẽ ra
  trace tương ứng.
- **Prompt name:** `LANGFUSE_PROMPT_NAME=day13-chat`.
- **Version/label baseline:** v1, labels `baseline` + `production`.
- **Version/label candidate:** v2, label `candidate`; đã promote `production` sang v2 rồi rollback `production` về v1.
- **Trace ID của mỗi version:** baseline v1 `7753daccd45ec6ac78091386860291f9`; candidate v2
  `de21375d0becac8384161055a4887546`; production v2 sau promote `4387e119a56e5ce1f255d1ac2917014e`;
  production v1 sau rollback `99e6265b30fbcc29d26698c29392045b`.
- **Trace production v1 hiện tại:** `1f0ea30a3f8054d04917db1774aeaff3` (`correlation_id=req-langfuse-current`).
- **Cách promote và rollback `production`:** dùng Langfuse SDK chuyển label `production` sang v2 rồi trả về v1;
  các trace trên xác nhận version được resolve. Ảnh UI `evidence/10-prompt-rollback.png` vẫn cần chụp thủ công;
  app chỉ đọc label qua `LANGFUSE_PROMPT_LABEL`, không tự đổi label.

Key chỉ nằm trong `.env` local (được Git ignore), không nằm trong source hoặc commit.

Mười trace từ load test đầu tiên:

```text
de53241f3c0ac1b9a6ece2970c43808f
5ea53b1aeef39cfab3a8d9960d731a05
bb2b9dc7a741a67bb15895ded5b1395d
18c202ecc8a2c833fe0be69bcdd61065
af8e7e11f29ad7dd5064ee3f841035cf
2cf6ef9058a4737df4aa28b5c011d094
333e3883876da025c81530dc4fa0a016
3de81e996843342dfcf07775ea9c76cf
6b32d8f0de4ab69e537c3a912480a19d
c4ebdd5499405705745a0343807840bb
```

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** contract giữ nguyên 6 panel trong `config/dashboard.yaml`
  (latency/TTFT, traffic, errors+retrieval, cost, tokens, quality), time range 60 phút, refresh 30 giây,
  mỗi panel có đơn vị và threshold. `python scripts/validate_dashboard.py` → `HỢP LỆ: 6/6 panel`.
  _Ảnh dashboard runtime (6 panel có dữ liệu) vẫn phải tự dựng và chụp._
- **SLO và lý do chọn:** `fast_successful_requests` = `count(event == "response_sent" and latency_ms <= 2000
  and tool_success == true) / count(event == "request_received")`, target 99.5% trong 28 ngày.
  Lý do chọn ngưỡng 2000 ms (thay vì 3000 ms của starter): baseline đo được P95 = 151 ms, còn khi bật
  incident `rag_slow` thì P95 = 2651 ms. Ngưỡng 3000 ms sẽ **không bao giờ** bị vi phạm trong lab nên SLO và
  alert latency sẽ im lặng đúng lúc cần cảnh báo. 2000 ms nằm giữa hai trạng thái, cao hơn baseline ~13 lần
  nên không cảnh báo nhầm, và trùng với trường `latency_threshold_ms` mà file challenge dùng.
- **Cách tính error budget:** `error_budget = 100% - target = 0.5%` tổng số request trong cửa sổ 28 ngày.
  Vì SLI này tính theo request, không quy đổi phần trăm đó thành phút; số request cho phép vượt SLI là
  `0.005 × tổng request trong 28 ngày` (`error_budget_unit: bad_requests` trong `config/slo.yaml`).
  Khi hết budget thì chỉ nhận fix giảm rủi ro và rollback, không phát hành prompt version mới.
  Cùng file khai báo guardrail: error rate ≤ 2%, cost/ngày ≤ 2.5 USD, quality ≥ 0.75, retrieval success ≥ 90%.
- **Ba alert và runbook tương ứng:** `config/alert_rules.yaml` khai báo `high_p95_latency` (critical, 10m/5m),
  `high_error_rate_and_retrieval_failure` (critical, 10m/5m) và `cost_budget_burn` (warning, 30m/1d) —
  tất cả là symptom-based, có `severity`, `duration`, `owner: day13-oncall`, `channel: slack`,
  `slack_channel: "#day13-alerts"` và trỏ tới `docs/alerts.md#alert-1..3`. Runbook trong `docs/alerts.md`
  ghi SLI/SLO liên quan, ảnh hưởng tới người dùng, ba bước kiểm tra đầu tiên (metric → log → trace),
  mitigation tạm thời và biện pháp phòng ngừa. `tests/test_ops_config.py` kiểm tra đủ trường bắt buộc,
  anchor runbook tồn tại và ngưỡng SLO khớp dashboard.
- **Quan sát đáng lưu ý:** `rag_slow` làm latency server-side 2651 ms, còn wall-clock client khi chạy
  `--concurrency 5` lên ~13.3 s vì request xếp hàng. Đây là lý do cần đọc `response_sent.latency_ms`
  (đã ghi sẵn trong log) thay vì đo ở client.

## 7. Điều tra challenge

Challenge chính thức `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, feature `monitoring`, incident `rag_slow`, ngưỡng 2000 ms) đã được chạy bằng `scripts/inject_incident.py` và `scripts/load_test.py --challenge --concurrency 5`. File config chính thức được giữ local và ignore bởi Git. Các PNG `12`–`14` là ảnh bổ trợ cũ chụp trước challenge, không phải ảnh của request challenge; số liệu gắn với challenge được chứng minh bằng các file `.txt` cùng số.

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`.
- **Khoảng thời gian điều tra:** 2026-09-29 16:54:19–16:54:37 (Asia/Ho_Chi_Minh), lượt đầu; request bất thường được chọn bắt đầu lúc 16:54:26.901.
- **Triệu chứng từ metrics:** 5/5 response của lượt đầu vượt ngưỡng 2000 ms; `latency_ms` từ 2652 đến 7766 ms (median 2652 ms), so với baseline khoảng 151 ms. Request đầu bị queue khi chạy concurrency=5.
- **Log line và correlation ID liên quan:** `response_sent`, `correlation_id=req-bb0d4434`, `feature=monitoring`, `latency_ms=2652`, `tool_success=true` (xem `evidence/13-incident-log.txt`).
- **Trace ID và span gây ảnh hưởng:** `c935b1db8c3ab23d3129783d584db67d`; root `lab-agent-run` 2.653 s, child `retrieval` 2.501 s, child `llm-generation` 0.151 s (xem `evidence/14-incident-trace.txt`).
- **Root cause:** incident `rag_slow` cố ý thêm khoảng 2.5 giây vào retrieval; trace xác nhận phần lớn latency nằm ở retriever, không phải generation.
- **Fix action:** tắt incident qua `scripts/inject_incident.py --disable`; health xác nhận `rag_slow=false`. Không sửa hoặc thay đổi file challenge.
- **Preventive measure:** giữ latency alert/SLO threshold 2000 ms, theo dõi P95 và drill-down metric → correlation ID → retrieval span; thêm regression test để latency retrieval vượt ngưỡng bị phát hiện.

Tham khảo để tự luyện trước (đã chạy và kiểm chứng, không thay thế challenge chính thức):

| Lệnh | Kết quả quan sát được |
|---|---|
| `python scripts/inject_incident.py --scenario rag_slow` + `load_test.py` | P95 151 ms → 2651 ms; span `retrieval` giãn ~2.5 s |
| `python scripts/inject_incident.py --scenario tool_fail` | HTTP 500, `request_failed.error_type=RuntimeError`, `tool_success=false`, span `retrieval` mức `ERROR` |
| `python scripts/inject_incident.py --scenario cost_spike` | `tokens_out` 83–166 (bình thường) → 360–548; `cost_usd` ~0.0013–0.0027 → 0.0055–0.0083 mỗi request |
| `python scripts/inject_incident.py --scenario <tên> --disable` | Tắt incident, metric trở lại baseline |

## 8. Giải thích và tự đánh giá

Phần này phải viết bằng trải nghiệm của bạn. Các gợi ý dựa trên source hiện có trong repo:

- **Một quyết định kỹ thuật quan trọng và lý do:** hạ ngưỡng latency SLO 3000 ms → 2000 ms sau khi đo
  thực tế; một threshold không vượt qua được bởi sự cố thì alert chỉ là hình vẽ trên giấy.
- **Một lỗi/blocker đã gặp:** `validate_logs.py` đọc toàn bộ `data/logs.jsonl`; log ghi trước khi sửa code
  vẫn được tính. Cách xử lý: lưu baseline, xoá/đổi tên file log, restart API, chạy lại load test.
- **Cách tìm nguyên nhân và xử lý:** metric (P95/error/cost) → log (`correlation_id`) → trace (span
  `retrieval` so với `llm-generation`) → root cause.
- **Cách hiểu luồng Metrics → Logs → Traces:** metric cho biết phạm vi và mức độ sự cố (5/5 request challenge vượt ngưỡng 2 giây); log cho biết request cụ thể qua `correlation_id`; trace nối cùng ID đó với các span, cho thấy retrieval chiếm 2.501 giây còn generation chỉ 0.151 giây.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** label/version giúp xác định chính xác prompt đang chạy và quay lại bản ổn định; token/cost cảnh báo tăng chi phí; SLO biến mục tiêu latency/success thành ngưỡng có thể theo dõi. Trong challenge này, SLO 2 giây bắt được regression retrieval.
- **Điều quan trọng nhất đã học:** tổng latency của request chưa đủ để biết cần sửa thành phần nào; phải nối metric, log và trace bằng một correlation ID để khoanh vùng root cause.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** ảnh prompt versions còn breadcrumb project cũ; ảnh UI dashboard chưa chứng minh đủ sáu panel; incident UI screenshots chưa có (artifact text đã đính kèm).

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.

## 10. Kết quả kiểm tra tự động (đã chạy trên source hiện tại)

```text
$ python -m pytest -q
..................................                                       [100%]
34 passed in 1.65s

$ python scripts/validate_dashboard.py
HỢP LỆ: 6/6 panel có trong dashboard contract.

$ python scripts/load_test.py          # 10 request, không bật Langfuse
[200] req-d8721714 | qa | 157.1ms   ... (10/10 thành công)

$ python scripts/validate_logs.py
Total log records analyzed: 112
Records with missing required fields: 0
Records with missing enrichment (context): 0
Unique correlation IDs found: 58
Potential PII leaks detected: 0
Estimated Score: 100/100
```

`data/logs.jsonl` hiện có 112 dòng, 58 correlation IDs và 0 PII leak; log validator đạt 100/100.
Hãy lưu/đổi tên log này trước khi chạy workload chụp evidence mới, nếu cần ảnh chỉ chứa một phiên.

## 11. Việc còn phải làm thủ công (bắt buộc)

1. **Langfuse screenshot:** trace list, waterfall và metadata đã có. Chụp lại prompt v1/v2/rollback trong
   project đã đổi tên; ảnh `09-prompt-versions.png` hiện tại vẫn ghi tên project cũ.
2. **Dashboard runtime:** ảnh dashboard Langfuse hiện có là bằng chứng bổ sung, chưa thay thế contract sáu
   panel từ `config/dashboard.yaml` (đặc biệt còn thiếu panel errors/retrieval success và TTFT). Hoàn thiện
   đủ sáu panel với time range, đơn vị và threshold rồi chụp lại.
3. **Practice incident (tuỳ chọn, đã có sẵn lệnh ở mục 7):** chụp metric → log → trace cho một incident
   practice để quen quy trình trước khi làm challenge.
4. **Challenge chính thức (CP3):** đã chạy và điền mục 7; ba artifact incident `.txt` có trong evidence. Ảnh UI incident vẫn nên chụp nếu rubric yêu cầu ảnh màn hình.
5. **Hoàn thiện thông tin cá nhân:** xác nhận tên/MSSV, repository URL/commit SHA, upload evidence vào
   `submission/evidence/`, rà `.env`/secret/PII, commit và push lên repo cá nhân.
