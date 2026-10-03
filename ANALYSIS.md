# Báo Cáo Phân Tích Thực Nghiệm & Đánh Giá Hệ Thống Memory

> **Dự án**: Phase 2, Track 3, Day 17 - Memory Systems for AI Agent  
> **Người thực hiện**: Trần Quốc Khánh  
> **Mục tiêu**: Phân tích định lượng dựa trên kết quả thực nghiệm từ Benchmark, chứng minh chuỗi logic 5 mắt xích kiến trúc bộ nhớ, giải quyết 4 câu hỏi của Bước 8 và đánh giá giải pháp Bonus (đạt mức 90–100 điểm theo `Rubric.md`).

---

## 1. Bảng Dữ Liệu Thực Nghiệm (Benchmark Results)

Toàn bộ phân tích trong tài liệu này dựa trên số liệu thực tế được đo lường tự động bởi `src/benchmark.py`:

### Bảng 1: Standard Benchmark (`data/conversations.json` - 10 phiên hội thoại thông thường, user `dungct`)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 4,255 | 24,993 | **0.0%** | 20.0% | 0 | 0 |
| **Advanced** | 1,919 | 22,629 | **100.0%** | 100.0% | 264 | 0 |

### Bảng 2: Long-Context Stress Benchmark (`data/advanced_long_context.json` - 1 phiên stress 16 lượt dài, user `dungct_stress`)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 703 | 24,896 | **0.0%** | 20.0% | 0 | 0 |
| **Advanced** | 751 | **13,482** *(giảm 45.8%)* | **100.0%** | 100.0% | 185 | **19** |

---

## 2. Chuỗi Logic 5 Mắt Xích Kiến Trúc Memory (Theo Rubric)

Mỗi mắt xích dưới đây được xây dựng theo cấu trúc 3 phần chặt chẽ: **(1) Số liệu thực nghiệm chống đỡ**, **(2) Cơ chế mã nguồn trong `src/` tạo ra số liệu đó**, và **(3) Giới hạn / đánh đổi hệ thống đi kèm**.

```mermaid
flowchart TD
    M1["1. Baseline không nhớ dài hạn<br/>(Recall = 0.0%)"] --> M2["2. Advanced thêm User.md<br/>(Recall = 100.0%)"]
    M2 --> M3["3. Hội thoại dài làm prompt cost tăng vọt<br/>(Baseline = 24,896 tokens)"]
    M3 --> M4["4. Compact memory kéo chi phí ngữ cảnh xuống<br/>(Advanced = 13,482 tokens, 19 compactions)"]
    M4 --> M5["5. Hệ thống phức tạp hơn, cần Guardrail<br/>(Lọc nhiễu & xử lý xung đột facts)"]
```

### Mắt xích 1: Baseline không có khả năng nhớ dài hạn
1. **Số liệu thực nghiệm**: Ở cả Bảng 1 (Standard) và Bảng 2 (Stress), chỉ số `Cross-session recall` của Baseline Agent đều là **0.0%**, và `Memory growth (bytes)` bằng **0**.
2. **Cơ chế trong code**: Trong `src/agent_baseline.py`, trạng thái phiên được quản lý cục bộ trong `self.sessions[thread_id]`. Khi `benchmark.py` đưa ra câu hỏi kiểm tra ở một thread mới (`thread_id = f"{conv_id}-recall-{idx}"`), Baseline khởi tạo một `SessionState` hoàn toàn rỗng. Do không có bất kỳ cơ chế lưu trữ bền vững ngoài bộ nhớ RAM của thread hiện tại, nó không thể truy xuất bất kỳ fact nào đã nói ở phiên trước.
3. **Giới hạn đi kèm**: Baseline hoàn toàn vô dụng đối với các bài toán trợ lý thông minh đòi hỏi tính cá nhân hóa (personalization) xuyên suốt vòng đời người dùng.

### Mắt xích 2: Advanced thêm `User.md` giúp Recall tăng vọt
1. **Số liệu thực nghiệm**: Chỉ số `Cross-session recall` của Advanced Agent đạt tuyệt đối **100.0%** trên cả 10 hội thoại của Standard Benchmark và 3 câu hỏi hóc búa của Stress Benchmark; `Memory growth (bytes)` ghi nhận **264 bytes** (Standard) và **185 bytes** (Stress).
2. **Cơ chế trong code**: Mỗi lượt người dùng gửi tin nhắn, `src/agent_advanced.py` gọi `extract_profile_updates()` để bóc tách các fact ổn định (tên, nơi ở, nghề nghiệp, sở thích...), sau đó gọi `UserProfileStore.upsert_facts()` ghi bền vững vào file `state/profiles/<user_id>/User.md`. Khi nhận câu hỏi ở thread mới, phương thức `_offline_response()` gọi `profile_store.facts(user_id)` để đọc lại hồ sơ từ ổ đĩa và trả lời chính xác thông tin.
3. **Giới hạn đi kèm**: Hệ thống phát sinh chi phí I/O đọc/ghi đĩa trên mỗi lượt chat và phụ thuộc vào chất lượng trích xuất entity; nếu trích xuất sai, lỗi sẽ bị "đóng băng" vào file markdown và làm sai lệch câu trả lời ở toàn bộ các phiên kế tiếp.

### Mắt xích 3: Hội thoại dài làm chi phí ngữ cảnh (Prompt cost) tăng đột biến
1. **Số liệu thực nghiệm**: Trong Bảng 2 (Stress), chỉ qua 16 lượt hội thoại của 1 phiên duy nhất, chỉ số `Prompt tokens processed` của Baseline đã chạm mức **24,896 tokens**, tương đương với tổng lượng ngữ cảnh của toàn bộ 10 cuộc hội thoại trong Standard cộng lại (24,993 tokens).
2. **Cơ chế trong code**: Trong `BaselineAgent._reply_offline()`, ngữ cảnh prompt được xây dựng bằng cách cộng dồn toàn bộ lịch sử: `context_text = "".join(m["content"] for m in session.messages) + message`. Khi hội thoại dài ra, mỗi lượt gửi mới đều phải kéo theo toàn bộ lịch sử thô phía trước, tạo thành chi phí ngữ cảnh tăng theo cấp số cộng $\mathcal{O}(N^2)$ theo số lượt hội thoại.
3. **Giới hạn đi kèm**: Ngữ cảnh phình to làm tăng nguy cơ vượt quá context window của LLM (Context Overflow), làm loãng khả năng chú ý (Attention Dilution) và khiến chi phí gọi API tăng phi mã.

### Mắt xích 4: Compact Memory giúp kéo mạnh chi phí ngữ cảnh xuống
1. **Số liệu thực nghiệm**: Trong Bảng 2 (Stress), `Prompt tokens processed` của Advanced giảm xuống chỉ còn **13,482 tokens** (tiết kiệm **45.8%** ngữ cảnh xử lý so với 24,896 của Baseline), trong khi kích hoạt **19 lần compactions**. Quan trọng là, `Agent tokens only` của Advanced (751 tokens) xấp xỉ Baseline (703 tokens), chứng minh việc tiết kiệm token xảy ra thuần túy ở phần xử lý ngữ cảnh đầu vào (Prompt).
2. **Cơ chế trong code**: `src/memory_store.py` cài đặt `CompactMemoryManager`. Khi tổng token tích lũy của thread vượt qua ngưỡng `threshold_tokens=800`, cơ chế nén tự động cắt các tin nhắn cũ hơn `keep_messages=4`, tóm tắt chúng qua `summarize_messages()`, và chỉ lưu trữ bản summary ngắn gọn cùng 4 tin nhắn gần nhất. Nhờ đó, prompt context của Advanced luôn được chặn trần bởi công thức: $Context = Tokens(User.md) + Tokens(Summary) + Tokens(RecentMessages)$.
3. **Giới hạn đi kèm**: Compaction là một phép nén có tổn thất (lossy compression). Các thông tin tiểu tiết không mang tính định danh người dùng (như số liệu độ cao máy bay X-59 29,500 feet hay xác suất El Nino 80%) sẽ bị tóm tắt ngắn lại và không còn nguyên văn ban đầu.

### Mắt xích 5: Hệ thống mạnh hơn nhưng phức tạp hơn, đòi hỏi Guardrail chặt chẽ
1. **Số liệu thực nghiệm**: Bộ dữ liệu Stress chứa đầy đủ các bẫy thực tế: đính chính nơi ở (*Huế $\rightarrow$ Đà Nẵng*), đính chính nghề (*Backend $\rightarrow$ MLOps*), thông tin công tác ngắn ngày (*Hà Nội*), và câu đùa (*Product Manager*). Advanced vẫn giữ vững **100.0% Recall** và dung lượng bộ nhớ duy trì ổn định ở **185 bytes**.
2. **Cơ chế trong code**: Nếu không có guardrail, khi người dùng nói *"Có lúc mình đùa chuyển sang product manager"* hay *"Hà Nội chỉ là nơi mình bay ra họp hai ngày"*, bộ trích xuất thông thường sẽ ghi đè `profession = product manager` và `location = Hà Nội`. Hệ thống đã bổ sung các bộ lọc ngữ nghĩa (Negative Filtering & Inquiry Detection) trong `extract_profile_updates()` để chỉ ghi nhận các phát ngôn khẳng định chắc chắn và bỏ qua các câu hỏi dò ngữ cảnh.
3. **Giới hạn đi kèm**: Các quy tắc heuristic càng phức tạp thì càng đòi hỏi chi phí bảo trì luật cao, có thể phát sinh false negatives nếu người dùng thay đổi ngữ cảnh bằng các cấu trúc câu tiếng Việt quá đặc thù.

---

## 3. Trả Lời 4 Câu Hỏi Trọng Tâm của Bước 8 (Guide.md)

### Câu hỏi 1: Vì sao Advanced có recall tốt hơn Baseline?
- **Dẫn chứng số liệu**: 
  - Bảng 1 (Standard): Advanced đạt **100.0%**, Baseline đạt **0.0%**.
  - Bảng 2 (Stress): Advanced đạt **100.0%**, Baseline đạt **0.0%**.
- **Giải thích đường đi của fact trong code**:
  1. Khi tin nhắn người dùng đến: `extract_profile_updates(message)` phân tích và bóc tách các fact ổn định (vd: tên "DũngCT", nơi ở "Huế").
  2. Fact được chuyển vào `UserProfileStore.upsert_facts()`, đồng bộ hóa tức thì vào file vật lý `state/profiles/<user_id>/User.md`.
  3. Khi sang thread mới (mã phiên khác biệt hoàn toàn), `BaselineAgent` chỉ kiểm tra session nội bộ của thread mới đó nên không thấy dữ liệu gì. Ngược lại, `AdvancedAgent._reply_offline()` đọc file `User.md` thông qua `self.profile_store.facts(user_id)` và tái tạo đầy đủ ngữ cảnh để trả lời chính xác 100% câu hỏi kiểm tra.

### Câu hỏi 2: Vì sao Advanced có thể tốn hơn ở hội thoại ngắn?
- **Dẫn chứng số liệu**: 
  - Bảng 1 (Standard): `Prompt tokens processed` của Advanced đạt **22,629 tokens**, chỉ thấp hơn Baseline (24,993) một khoảng rất nhỏ (~9.4%), trong khi ở các hội thoại ngắn chỉ 1–2 lượt, Advanced phải nạp thêm toàn bộ nội dung `User.md` vào prompt.
  - Số lần Compactions ở Bảng 1 là **0 lần** cho cả hai agent.
- **Giải thích bằng cơ chế mã nguồn**:
  - Mỗi lượt chat của Advanced Agent, hàm `_estimate_prompt_context_tokens()` luôn phải cộng thêm `Tokens(User.md)`.
  - Trong các hội thoại ngắn (khoảng 10 lượt ngắn như trong `conversations.json`), tổng dung lượng token của thread chưa từng chạm tới ngưỡng `compact_threshold_tokens=800`.
  - Do cơ chế compact **chưa từng được kích hoạt**, Advanced không thu được lợi ích từ việc cắt giảm lịch sử tin nhắn, trong khi vẫn phải chịu chi phí overhead của file profile và chi phí I/O ghi đĩa trên từng turn.

### Câu hỏi 3: Vì sao Compact có lợi thế ở hội thoại dài?
- **Dẫn chứng số liệu**:
  - Bảng 2 (Stress - 16 lượt dài): `Prompt tokens processed` của Advanced là **13,482 tokens**, giảm vượt trội **45.8%** so với mức **24,896 tokens** của Baseline.
  - `Agent tokens only` của hai bên tương đương nhau: Advanced là **751 tokens**, Baseline là **703 tokens** (chênh lệch không đáng kể do style trả lời 3 bullet).
- **Phân định rõ ranh giới hai cột theo Rubric**:
  - Compact Memory **không tối ưu cột `Agent tokens only`** vì số token do Agent sinh ra phụ thuộc vào nội dung câu trả lời của mô hình.
  - Compact Memory **tối ưu trực tiếp cột `Prompt tokens processed`**. Thay vì bắt Agent phải đọc lại 16 lượt tin nhắn dài với hàng ngàn chữ ở turn cuối, Compact Memory đã nén lịch sử qua **19 lần compaction**, giữ cho kích thước prompt đầu vào luôn ở mức ổn định quanh ngưỡng 800 tokens.

### Câu hỏi 4: File memory tăng trưởng ra sao và rủi ro gì đi kèm?
- **Dẫn chứng số liệu**:
  - `Memory growth (bytes)`: Tăng **264 bytes** (Standard) và **185 bytes** (Stress).
- **Phân tích rủi ro thực tế quan sát được**:
  1. **Rủi ro phình to dữ liệu (Storage Bloat & Context Leak)**: Mặc dù ở bài lab dung lượng chỉ tăng khoảng 200 bytes do số lượng entity hạn chế, nhưng trong hệ thống production chạy nhiều tháng, nếu lưu trữ phi cấu trúc mọi câu nói của người dùng, file `User.md` sẽ phình to lên hàng trăm KB, biến chính persistent memory thành một nguồn gây tràn context window mới.
  2. **Rủi ro ô nhiễm dữ liệu (Memory Poisoning & Hallucination Lock-in)**: Nếu người dùng đặt câu hỏi giả định hoặc đưa thông tin đùa (*"Mình vừa trúng số 100 tỷ"*, *"Đùa chuyển sang làm product manager"*), nếu không có guardrail tin cậy, fact sai này sẽ bị ghi đè vĩnh viễn vào `User.md`, làm hỏng toàn bộ các quyết định về sau của Agent.

---

## 4. Phần Triển Khai Bonus (Mức Điểm 90–100 Theo Rubric)

Nhằm đạt mức điểm tối đa (90–100) theo tiêu chí của `Rubric.md`, bài làm đã chọn và hoàn thiện **02 giải pháp Bonus kỹ thuật thực tế** trong `src/memory_store.py` và kiểm chứng qua unit test `test_confidence_and_conflict_handling` trong `src/test_agents.py`:

```
                       ┌──────────────────────────────┐
                       │  User Message / Input Turn   │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
               ┌──────────────────────────────────────────────┐
               │    Guardrail 1: Question & Inquiry Filter    │
               │  (Confidence = 0.0 nếu là câu hỏi kiểm tra)  │
               └──────────────┬───────────────────────────────┘
                              │
                      [Confidence >= 0.7?]
                             / \
                       No   /   \  Yes
                           /     \
                          ▼       ▼
                    [Reject]   ┌────────────────────────────────────────┐
                               │     Guardrail 2: Noise & Joke Filter   │
                               │ (Loại bỏ câu đùa, địa điểm công tác)   │
                               └──────────────────┬─────────────────────┘
                                                  │
                                                  ▼
                               ┌────────────────────────────────────────┐
                               │   Bonus 3: Conflict Resolution Engine  │
                               │  (Ghi đè fact mới, xóa bỏ fact cũ sai) │
                               └──────────────────┬─────────────────────┘
                                                  │
                                                  ▼
                                       ┌─────────────────────┐
                                       │       User.md       │
                                       └─────────────────────┘
```

---

### Bonus 1: Conflict Resolution & Correction Handling (Xử lý xung đột & Đính chính facts)

#### 1. Bonus này giải quyết vấn đề gì?
Trong thực tế, thông tin cá nhân của người dùng luôn thay đổi theo thời gian (đổi chỗ ở, đổi nghề nghiệp, cập nhật sở thích). Nếu hệ thống memory chỉ lưu dạng log tuần tự hoặc append đơn thuần, file `User.md` sẽ chứa cả hai thông tin mâu thuẫn:
- *Vừa ở Đà Nẵng, vừa ở Huế.*
- *Vừa là backend engineer, vừa là MLOps engineer.*

Khi LLM đọc một hồ sơ mâu thuẫn như vậy, nó sẽ rơi vào trạng thái hallucination hoặc chọn ngẫu nhiên fact cũ.

#### 2. Cải thiện recall và token cost như thế nào?
- **Về Recall**: Trong `conversations.json`, người dùng ban đầu ở Đà Nẵng (Conv 1), sau đó đính chính chuyển về Huế (Conv 3). Tương tự, nghề nghiệp đổi từ backend sang MLOps (Conv 6). Cơ chế `UserProfileStore.upsert_facts()` tổ chức profile theo dạng key-value chuẩn (`- **location**: Huế`, `- **profession**: MLOps engineer`). Khi có đính chính mới, fact cũ lập tức bị thay thế hoàn toàn. Nhờ đó, ở câu hỏi tổng hợp Conv 10, Agent đạt **100% recall** với đầy đủ các fact mới nhất.
- **Về Token Cost**: Bằng cách ghi đè thay vì append lũy tiến, kích thước `User.md` được chặn trần cố định (chỉ tăng **185–264 bytes**), không gây lãng phí prompt token cho các thông tin đã lỗi thời.

#### 3. Rủi ro tạo thêm cho hệ thống là gì?
- **Mất dấu vết lịch sử (Lack of Provenance)**: Việc đè hoàn toàn giá trị mới làm mất đi dòng thời gian (temporal timeline). Agent sẽ không biết người dùng đã từng ở Đà Nẵng vào thời điểm nào nếu sau này người dùng hỏi: *"Trước khi về Huế mình từng ở đâu?"*.

---

### Bonus 2: Confidence Threshold & Question Guardrail (Ngưỡng tin cậy & Chống ô nhiễm từ câu hỏi)

#### 1. Bonus này giải quyết vấn đề gì?
Người dùng thường xuyên đưa ra các câu hỏi kiểm tra bộ nhớ hoặc câu nói đùa:
- *"Nếu ai đó nhắc Huế, Hà Nội hay product manager, đâu mới là nghề nghiệp và nơi ở hiện tại của mình?"*
- *"Có lúc mình đùa chuyển sang product manager... nhưng đó chỉ là câu đùa."*
- *"Hà Nội chỉ là nơi mình vừa bay ra họp hai ngày với đối tác chứ không phải nơi ở hiện tại."*

Nếu không có guardrail phân loại ý định, bộ trích xuất sẽ nhận diện từ khóa "product manager" hay "Hà Nội" và cập nhật đè làm sai lệch toàn bộ hồ sơ.

#### 2. Cải thiện recall và token cost như thế nào?
- **Về Recall**: Hàm `extract_profile_updates(message, min_confidence=0.7)` tích hợp bộ lọc hai tầng:
  1. *Inquiry Detection*: Nếu câu có dấu hỏi `?` và chứa các từ khóa truy vấn (`đâu mới là`, `nhắc lại`, `bạn có biết`), điểm confidence gán bằng `0.0`, ngăn chặn tuyệt đối việc tự học từ chính câu hỏi kiểm tra.
  2. *Negative/Transient Context Detection*: Bỏ qua các địa danh đi kèm ngữ cảnh công tác ngắn hạn (`chỉ là nơi bay ra họp`) hoặc câu đùa (`chỉ là câu đùa`).
  Nhờ đó, ở Bảng 2 (Stress), Agent duy trì recall **100.0%** tuyệt đối trước 3 câu hỏi kiểm tra mang tính đánh đố cao.
- **Về Token Cost**: Ngăn chặn rác dữ liệu được nạp vào `User.md`, giữ cho prompt context luôn tinh gọn.

#### 3. Rủi ro tạo thêm cho hệ thống là gì?
- **Nguy cơ False Negatives**: Nếu người dùng vô tình đặt một câu hỏi phức hợp có chứa fact mới thật sự (ví dụ: *"Mình vừa chuyển nhà sang Cần Thơ tuần trước, bạn có biết quán cà phê nào ngon ở đó không?"*), hệ thống có thể đánh giá nhầm đây là câu hỏi thuần túy và bỏ qua fact nơi ở mới "Cần Thơ".

---

## 5. Bằng Chứng Xác Minh Tự Động (Automated Verification)

Hệ thống được xác minh bằng 5 bài kiểm thử tự động với Pytest và chạy benchmark thành công 100%:

```bash
$ pytest src/test_agents.py -v
============================= test session starts =============================
collected 5 items

src/test_agents.py::test_user_markdown_read_write_edit PASSED            [ 20%]
src/test_agents.py::test_compact_trigger PASSED                          [ 40%]
src/test_agents.py::test_cross_session_recall PASSED                     [ 60%]
src/test_agents.py::test_compact_reduces_prompt_load_on_long_thread PASSED [ 80%]
src/test_agents.py::test_confidence_and_conflict_handling PASSED         [100%]
============================== 5 passed in 0.08s ==============================
```

---

## 6. Kết Luận & Đúc Kết Kiến Trúc

Thực nghiệm trên hai bộ dữ liệu Standard và Long-Context Stress đã chứng minh toàn diện:
1. **Short-term memory là chưa đủ**: Baseline Agent không thể duy trì ngữ cảnh cá nhân hóa qua các phiên độc lập.
2. **Persistent Memory (`User.md`) là giải pháp bắt buộc** để giải quyết bài toán Cross-session Recall với chi phí lưu trữ tối thiểu (chỉ vài trăm bytes).
3. **Compact Memory là chìa khóa sống còn cho Scalability**: Nén hội thoại cũ giúp giảm tải gần **50% Prompt tokens** trong hội thoại dài, ngăn chặn việc bùng nổ chi phí token và hiện tượng loãng ngữ cảnh.
4. **Hệ thống memory tin cậy luôn phải song hành với Guardrail**: Các cơ chế Confidence Threshold và Conflict Resolution đóng vai trò cốt lõi để giữ cho bộ nhớ dài hạn luôn sạch và chính xác trước nhiễu thực tế.
