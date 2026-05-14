# Release Notes

---

## v0.3.1 — Wiki Graph Department Clusters (2026-05-14)

**Tính năng mới**

Wiki Graph (`/wiki/graph`) nay hiển thị các cụm phòng ban rõ ràng:

- Mỗi phòng ban được bao bởi một hull mờ với màu riêng — tương tự cách project được hiển thị.
- Các trang wiki của cùng phòng ban được kéo về phía nhau trong simulation, tạo thành cụm tự nhiên thay vì trải đều.
- Legend liệt kê từng phòng ban với số trang. Tooltip hiển thị tên phòng ban khi hover vào trang scoped.

**Lưu ý triển khai**: Không cần migration. Chỉ cần rebuild frontend.

---

## v0.3.0 — Department Wiki Isolation + MRP Improvements (2026-05-13)

**Tính năng mới**

### Wiki cách ly theo phòng ban

Tài liệu nguồn gắn phòng ban → wiki pages được biên soạn ra chỉ hiện với thành viên phòng ban đó.

- Người dùng thấy wiki global (không phòng ban) + wiki của phòng ban mình.
- Admin thấy tất cả.
- Đổi phòng ban của nguồn tài liệu → pipeline tự chạy lại, wiki cũ được dọn, wiki mới ở phòng ban mới.
- Giao diện edit source có dialog xác nhận trước khi đổi phòng ban.

### Plan regeneration với reviewer feedback

Admin review kế hoạch biên soạn có thể từ chối và để lại ghi chú → AI tái tạo kế hoạch tích hợp phản hồi đó. Nút *Regenerate* trong Plan Review Dialog.

### Model catalog cho LLM & Vision

Thay vì nhập tự do tên provider + model, admin chọn từ danh sách được quản lý với đầy đủ metadata: context window, giá, hỗ trợ tool/vision/thinking.

- Trang Settings hiện thị card cho từng model với thông tin chi tiết.
- Gemini 3.1 Flash Lite là model mới được khuyến nghị cho extraction và caption ảnh (1M context, rẻ nhất).

**Lưu ý triển khai**:
- Chạy `alembic upgrade head` trước khi deploy v0.3.0.
- Admin đang dùng `gemini-3.1-flash` cần vào Settings → LLM Model và chọn lại model sau khi upgrade (model cũ đã bị xóa khỏi catalog).

**Sửa lỗi quan trọng**

- Pipeline không còn re-run toàn bộ REFINE phase khi resume từ VERIFY/COMMIT.
- Caption ảnh được bake vào source trước khi MAP chạy — sửa lỗi image marker rỗng trong wiki.
- KB reconciliation tìm đúng scope, tránh tạo trang trùng lặp.
- Từ ngắn (VD: "AI") không còn match nhầm subject không liên quan ("MAIL") khi đối chiếu evidence.
