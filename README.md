# Đồ án Mạng máy tính: Hệ thống truyền nhận file qua Socket

Dự án này mô phỏng một dịch vụ chia sẻ file nội bộ, xây dựng một ứng dụng client-server hoàn chỉnh bằng Python, sử dụng giao thức TCP và một giao thức tùy chỉnh ở tầng ứng dụng.

## Mục tiêu kỹ thuật

- **Socket API tầng TCP**: Sử dụng các hàm socket cơ bản để tạo kết nối.
- **Message Boundary**: Tự thiết kế cơ chế đóng khung (framing) để giải quyết vấn đề của giao thức stream.
- **Thiết kế giao thức**: Xây dựng giao thức tầng ứng dụng tùy chỉnh có cấu trúc nhị phân rõ ràng.
- **I/O đồng thời**: Server có khả năng phục vụ nhiều client cùng lúc bằng cách sử dụng `threading`.
- **Tính toàn vẹn & chịu lỗi**: Đảm bảo file được truyền đúng và đủ bằng checksum, đồng thời xử lý các lỗi phát sinh như mất kết nối.

## Tổng quan chức năng

Hệ thống cung cấp các chức năng cốt lõi của một dịch vụ lưu trữ và chia sẻ file cơ bản:

-   **Xác thực người dùng**: Client đăng nhập vào hệ thống bằng `username` và `user_id`. Mỗi người dùng có một không gian lưu trữ riêng trên server.
-   **Quản lý file từ xa**:
    -   **Liệt kê file (`list`)**: Xem danh sách các file đã có trên server.
    -   **Tải file lên (`upload`)**: Tải một file từ máy local lên server.
    -   **Tải file xuống (`download`)**: Tải một file từ server về máy local.
    -   **Xóa file (`delete`)**: Xóa một file khỏi server.
-   **Phục hồi truyền file (Resume)**: Cả quá trình upload và download đều có khả năng tự động phục hồi nếu bị gián đoạn, giúp tiết kiệm thời gian và băng thông.
-   **Giới hạn băng thông (Rate Limiting)**: Có thể cấu hình tốc độ upload/download tối đa để kiểm soát việc sử dụng tài nguyên mạng.
-   **Hỗ trợ nhiều người dùng**: Server được thiết kế để phục vụ nhiều client kết nối và hoạt động đồng thời.

## Kiến trúc hệ thống

Sơ đồ dưới đây mô tả kiến trúc tổng quan của hệ thống, bao gồm các thành phần chính và luồng tương tác giữa chúng.

```mermaid
graph TD
    subgraph "Client Application"
        A[Client]
    end

    subgraph "Server Application"
        B(Main Server Thread)
        C{Client Handler Threads}
    end

    subgraph "Protocol Modules (./protocol)"
        P[protocol/ <br/> opcode.py, packet.py, framing.py, payload.py]
    end

    subgraph "Common Components"
        U[common/ <br/> checksum.py, logger.py, config.py, storage.py]
        FS[(File System <br/> storage/)]
    end

    A -- "1. TCP Connect" --> B
    B -- "2. Spawns Thread" --> C
    A -- "3. Gửi/Nhận Packet" --> C
    
    C -- "4. Xử lý logic" --> C
    C -- "Đọc/Ghi file" --> FS
    C -- "Sử dụng modules" --> U

    A -- "Đóng/Mở gói" --> P
    C -- "Đóng/Mở gói" --> P
```

**Luồng hoạt động chính:**
1.  **Server** khởi động luồng chính (`Main Server Thread`) để lắng nghe kết nối mới trên một cổng xác định.
2.  Khi một **Client** thực hiện kết nối, luồng chính của Server chấp nhận và tạo ra một luồng xử lý riêng (`Client Handler Thread`) để phục vụ riêng cho client đó.
3.  **Client** và **Client Handler** tương ứng giao tiếp với nhau bằng cách gửi và nhận các gói tin (`Packet`) theo một giao thức tùy chỉnh.
4.  Các **Module Giao thức** (`Protocol Modules`) chịu trách nhiệm đóng gói (`pack`) dữ liệu thành `Packet` trước khi gửi và giải mã (`unpack`) `Packet` khi nhận. Nó cũng xử lý vấn đề `message boundary` bằng kỹ thuật `length-prefixed framing`.
5.  **Client Handler** dựa vào `opcode` trong gói tin để thực hiện các yêu cầu của client (ví dụ: `LOGIN`, `FILE_UPLOAD`).
6.  Trong quá trình xử lý, `Client Handler` tương tác với **Hệ thống file** (`File System`) để lưu/đọc file trong thư mục `storage/<username>` và sử dụng các **Module chung** (`common/`) như ghi log, tính checksum.

## Cấu trúc thư mục

```
FileTransfer/
├── logs/                   # Thư mục chứa file log
│   └── server.log
│
├── storage/                # Thư mục server lưu file của các user
│   └── <username>/
│
├── protocol/               # Module định nghĩa giao thức tùy chỉnh
│   ├── opcode.py           # Định nghĩa các mã lệnh (opcode)
│   ├── packet.py           # Định nghĩa cấu trúc gói tin
│   ├── framing.py          # Xử lý đóng khung (gửi/nhận toàn vẹn 1 gói tin)
│   └── payload.py          # Encode/decode dữ liệu trong gói tin
│
├── common/                 # Các module tiện ích chung
│   ├── checksum.py         # Hàm tính checksum cho file
│   ├── config.py           # File cấu hình (HOST, PORT, ...)
│   ├── logger.py           # Module thiết lập ghi log
│   └── storage.py          # Module lưu trữ file
│
├── file_transfer/          # Module xử lý truyền file
│   └── file_transfer.py
│
├── .client_state.json      # File lưu trạng thái đăng nhập
├── client.py               # Chương trình client
├── server.py               # Chương trình server
├── config.py               # File cấu hình (HOST, PORT, ...)
├── README.md               # File mô tả dự án
```

## Cơ chế kỹ thuật

### 1. Xử lý Message Boundary với Length-Prefixed Framing

- **Cơ chế**: Dự án sử dụng kỹ thuật **Length-Prefixed Framing**. Trước khi gửi một gói tin logic, hệ thống sẽ tính toán tổng kích thước của nó và gửi con số này đi trước dưới dạng một tiêu đề có độ dài cố định (4-byte `LENGTH`).
- **Luồng hoạt động**:
    1.  **Bên gửi**: Đóng gói dữ liệu vào `Packet`, tính tổng kích thước (`OPCODE` + `USER_ID` + `PAYLOAD`), sau đó gửi `[LENGTH (4 bytes)][Packet]` qua socket.
    2.  **Bên nhận**: Trước tiên, đọc chính xác 4 byte đầu tiên để biết được kích thước `LENGTH` của gói tin đang chờ. Sau đó, tiếp tục đọc từ socket cho đến khi nhận đủ `LENGTH` byte. Tại thời điểm này, bên nhận chắc chắn đã có một gói tin hoàn chỉnh và có thể bắt đầu xử lý nó.
- **Lý do lựa chọn**:
    - **Đơn giản và hiệu quả**: Đây là một trong những phương pháp tiêu chuẩn và hiệu quả nhất để giải quyết vấn đề message boundary trên TCP.
    - **An toàn với dữ liệu nhị phân**: So với việc dùng ký tự phân tách (delimiter), phương pháp này an toàn tuyệt đối vì nó không quan tâm đến nội dung của payload. Một ký tự phân tách có thể vô tình xuất hiện trong dữ liệu file nhị phân, gây lỗi nghiêm trọng.

### 2. Đảm bảo Toàn vẹn File với Checksum SHA-256

- **Vấn đề**: Trong quá trình truyền qua mạng, dữ liệu file có thể bị thay đổi hoặc mất mát do lỗi đường truyền, dẫn đến file bị hỏng ở phía người nhận.
- **Cơ chế**:
    1.  **Bên gửi (Client)**: Trước khi bắt đầu upload, client tính toán giá trị băm (hash) của toàn bộ file bằng thuật toán **SHA-256**. Giá trị hash này (gọi là `checksum`) được gửi đến server cùng với các siêu dữ liệu khác (tên file, kích thước).
    2.  **Bên nhận (Server)**: Sau khi nhận tất cả các chunk của file, server cũng tính toán lại checksum SHA-256 trên file vừa nhận được.
    3.  **Xác thực**: Server so sánh checksum mà nó tính được với checksum mà client đã gửi. Nếu hai giá trị khớp nhau, file đã được truyền thành công và toàn vẹn. Nếu không, server sẽ báo lỗi.
- **Lý do lựa chọn**:
    - **Độ tin cậy cao**: SHA-256 là một thuật toán băm mật mã học. Khả năng hai file khác nhau tạo ra cùng một giá trị hash (xung đột - collision) là cực kỳ thấp, đảm bảo việc phát hiện lỗi gần như tuyệt đối.
    - **Hiệu quả với file lớn**: Việc tính checksum được thực hiện bằng cách đọc file theo từng chunk nhỏ, giúp ứng dụng không tiêu tốn quá nhiều bộ nhớ, ngay cả khi xử lý các file có dung lượng hàng gigabyte.

### 3. Giới hạn băng thông (Rate Limiting)

-   **Vấn đề**: Một phiên truyền file (upload/download) có thể chiếm toàn bộ băng thông mạng có sẵn của client hoặc server, làm ảnh hưởng đến các tác vụ khác và gây ra trải nghiệm không tốt.
-   **Cơ chế**:
    1.  Hệ thống sử dụng một lớp `RateLimiter` để thực hiện việc điều tiết tốc độ.
    2.  Trước khi bắt đầu một phiên truyền file, một đối tượng `RateLimiter` được tạo ra với tốc độ tối đa được cấu hình trong `config.py` (`CLIENT_UPLOAD_RATE_KBPS` cho client và `SERVER_UPLOAD_RATE_KBPS` cho server).
    3.  Đối tượng này được truyền vào hàm `send_file_chunks` và sau đó là `send_packet`.
    4.  Sau mỗi lần gửi một gói tin (chunk), `RateLimiter` sẽ tính toán lượng dữ liệu đã gửi và thời gian đã trôi qua. Nếu tốc độ hiện tại vượt quá giới hạn, nó sẽ cho luồng hiện tại "ngủ" (`time.sleep()`) một khoảng thời gian ngắn để hãm tốc độ trung bình lại.
-   **Lý do lựa chọn**:
    -   **Đơn giản và hiệu quả**: Đây là một cách triển khai thuật toán "token bucket" ở mức cơ bản, dễ hiểu và không cần thư viện bên ngoài.
    -   **Kiểm soát linh hoạt**: Cho phép cấu hình các giới hạn tốc độ khác nhau cho việc upload của client và download từ server, phù hợp với các mô hình mạng bất đối xứng phổ biến.
    -   **Áp dụng trên từng kết nối**: Việc giới hạn được áp dụng riêng cho mỗi phiên truyền file, giúp đảm bảo sự công bằng giữa các client đang hoạt động đồng thời.

### 4. Lựa chọn các tham số hệ thống

Các hằng số trong `config.py` được chọn dựa trên sự cân bằng giữa hiệu năng, tài nguyên và trải nghiệm người dùng.

-   **`CHUNK_SIZE = 4096` (4KB)**
    -   **Lý do**: Đây là một kích thước phổ biến cho các khối (block) trong hệ thống file và trang bộ nhớ (memory page).
    -   **Cân bằng**:
        -   **Nếu quá nhỏ**: Sẽ làm tăng gánh nặng (overhead) do mỗi chunk phải được gói trong một packet riêng, dẫn đến nhiều lệnh gọi hệ thống và header mạng hơn.
        -   **Nếu quá lớn**: Sẽ chiếm nhiều bộ nhớ đệm và có thể làm cho việc giới hạn băng thông (rate limiting) kém chính xác hơn, cũng như khiến thanh tiến trình (progress bar) cập nhật không mượt mà.
    -   **Kết luận**: 4KB là một giá trị cân bằng, hiệu quả cho hầu hết các điều kiện mạng thông thường.

-   **`SERVER_UPLOAD_RATE_KBPS = 1024` và `CLIENT_UPLOAD_RATE_KBPS = 512`**
    -   **Lý do**: Các giá trị này được đặt ra để minh họa cho tính năng giới hạn băng thông và đảm bảo sự công bằng giữa các client.
    -   **`SERVER_UPLOAD_RATE_KBPS` (1MB/s)**: Giới hạn tốc độ server gửi dữ liệu (client download). Mức này đủ nhanh để mang lại trải nghiệm tốt nhưng cũng đủ thấp để một client không chiếm hết toàn bộ băng thông của server.
    -   **`CLIENT_UPLOAD_RATE_KBPS` (512KB/s)**: Giới hạn tốc độ client gửi dữ liệu. Mức này thấp hơn vì trong thực tế, băng thông upload của người dùng thường hạn chế hơn download. Việc giới hạn giúp client không bị "treo" các tác vụ mạng khác.

-   **`MAX_CONCURRENT_CLIENTS = 50`**
    -   **Lý do**: Đây là một biện pháp quản lý tài nguyên để ngăn server bị quá tải. Mỗi client kết nối sẽ tiêu tốn một luồng (thread), bộ nhớ và một file descriptor.
    -   **Cân bằng**: Con số 50 là một ước tính an toàn cho một server chạy trên một máy tính thông thường. Nếu đặt quá cao, server có thể cạn kiệt bộ nhớ hoặc CPU do phải chuyển đổi ngữ cảnh liên tục giữa các luồng. Nếu quá thấp, server sẽ không tận dụng hết tài nguyên.
    -   **Kết luận**: Giá trị này nên được điều chỉnh tùy theo cấu hình phần cứng của server và khối lượng công việc dự kiến.

## Quy tắc hệ thống

### 1. Xử lý File không hợp lệ
Cơ chế này đảm bảo tính nhất quán và an toàn cho dữ liệu trên server.
- **Khi Upload**:
    - **File đã tồn tại**: Server sẽ từ chối upload nếu file trên server có kích thước lớn hơn hoặc bằng file client đang gửi. Nếu file trên server nhỏ hơn, cơ chế upload tiếp (resume) sẽ được kích hoạt.
    - **Lỗi toàn vẹn dữ liệu**: Sau khi nhận xong file, server sẽ tính toán và so sánh `checksum SHA-256`. Nếu không khớp với giá trị client gửi, server sẽ báo lỗi cho client và quá trình upload xem như thất bại.
- **Khi Download hoặc Xóa**:
    - **File không tồn tại**: Nếu client yêu cầu một file không có trong kho lưu trữ của mình, server sẽ gửi lại thông báo lỗi "File not found".

### 2. Xử lý khi vượt giới hạn Client
Cơ chế này giúp server hoạt động ổn định, không bị quá tải bởi quá nhiều kết nối đồng thời.
- **Cơ chế**: Server sử dụng một `Semaphore` để giới hạn số lượng client kết nối cùng lúc, được cấu hình bởi `MAX_CONCURRENT_CLIENTS`.
- **Luồng xử lý**:
    1. Khi có kết nối mới, server sẽ kiểm tra xem `Semaphore` còn "suất" trống hay không.
    2. Nếu hết suất: Kết nối sẽ bị từ chối ngay lập tức. Server gửi một gói tin lỗi "Server at full capacity" và đóng kết nối.
    3. Nếu còn suất: Kết nối được chấp nhận và một luồng xử lý riêng được tạo ra để phục vụ client.
    4. Khi client ngắt kết nối, "suất" sẽ được trả lại cho `Semaphore`, cho phép một client khác kết nối.

## Hướng dẫn chạy

1.  **Chạy Server**

    Mở terminal và thực thi lệnh:
    ```bash
    python server.py
    ```
    Server sẽ bắt đầu lắng nghe kết nối tại địa chỉ và cổng được định nghĩa trong `config.py`.

2.  **Chạy Client**

    Mở một terminal khác. Để đăng nhập, sử dụng lệnh:
    ```bash
    python client.py login <username> <user_id> [--interactive]
    ```
    Ví dụ:
    ```bash
    python client.py login alice 101
    ```

---
## Bảng kiểm chứng
| Phân loại File | Lần kiểm thử | Thời gian truyền(s) | Tốc độ truyền | CPU trung bình(%) | RAM trung bình (MB) |
|---|---|---|---|---|---|
| File nhỏ (< 1MB):<br>Images.jfif<br>(20KB) | Lần 1 | 0.021 | 929.77 KB/s | 4.0 | 8.0 MB |
| | Lần 2 | 0.002 | 9664.13 KB/s | 2.0 | 3.0 MB |
| | Lần 3 | 0.010 | 2044.35 KB/s | 16.0 | 2.5 MB |
| | **Trung bình** | 0.011 | 4212.75 KB/s | 7.3 | 4.5 MB |
| File vừa (~ 1 MB -> 10 MB):<br>  | Lần 1 | 0.007 | 55221.95 KB/s | 2.0 | 0.5 MB |
| | Lần 2 | 0.013 | 28051.52 KB/s | ~1.0 | 3.0 MB |
| | Lần 3 | 0.011 | 33280.92 KB/s | 2.0 | 3.0 MB |
| | **Trung bình** | 0.031 | 38851.46 KB/s | 1.6 | 6.5 MB |
| File lớn (>= 10 MB) | Lần 1 | 1701s | 1016.72 KB/s | 16 | 3 MB |
| | Lần 2 | 1481 | 1167.87 KB/s | 14 | 2 MB |
| | Lần 3 | 1578 | 1095.83 KB/s | 13 | 3 MB |
| | **Trung bình** | 1586.67 | 1093.47 KB/s | 14.3 | 2.67 MB |