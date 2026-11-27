# Phần cứng Raspberry Pi

Driver trong `pi/` chạy trên Raspberry Pi OS bằng GPIO Zero. Chân được cấu hình theo số BCM; có thể đổi bằng biến môi trường như `TRIG_PIN` hoặc `PIR_PIN`.

| Linh kiện | BCM | Chân vật lý Pi |
|---|---:|---:|
| HC-SR04 TRIG | GPIO 23 | 16 |
| HC-SR04 ECHO | GPIO 24 | 18 |
| PIR OUT | GPIO 17 | 11 |
| LED xanh (qua điện trở) | GPIO 27 | 13 |
| LED đỏ (qua điện trở) | GPIO 22 | 15 |
| LCD SDA | GPIO 2 | 3 |
| LCD SCL | GPIO 3 | 5 |

Nối chung GND giữa Pi, cảm biến và LCD. Chân ECHO của HC-SR04 phát mức 5 V; phải qua cầu phân áp để đưa tín hiệu về mức an toàn cho GPIO 3.3 V của Pi. Mỗi LED cần điện trở hạn dòng. LCD I2C mặc định dùng địa chỉ `0x27`, có thể đổi bằng `LCD_I2C_ADDRESS` (ví dụ `0x3f`).

Kiểm tra lại địa chỉ LCD bằng `i2cdetect -y 1`. Bật I2C trong `raspi-config` nếu chưa bật. Không cấp tín hiệu 5 V trực tiếp vào GPIO Raspberry Pi.

## Kiểm tra tại chỗ

Trước tiên chạy smoke check không dùng GPIO:

```bash
python -m pi.main --mock --no-server --seconds 5 --console
```

Sau đó chạy trên Pi thật với `API_URL` và `API_KEY` đã đặt. Lúc khởi động để lối đi thông thoáng trong lúc cảm biến lấy khoảng cách nền; PIR cần khoảng 30 giây ổn định sau khi cấp nguồn.
