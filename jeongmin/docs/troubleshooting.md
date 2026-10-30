# 라즈베리파이·라즈봇 문제 해결 기록

발표의 "한계와 해결" 슬라이드 재료. 겪은 순서대로.

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| 라즈베리파이를 노트북 USB 에 꽂아도 노트북에서 아무 장치도 안 보임 | 라즈베리파이 5 의 USB-C 는 **전원 전용** | 정상. 접속은 Wi-Fi + SSH 로 한다 |
| 노트북 USB 전원으로 켜면 불안정할 수 있음 | 라즈베리파이 5 는 5V 3~5A 필요, 노트북 USB 는 부족 | 충전기(PD) 사용. `vcgencmd get_throttled` 가 `0x0` 이면 전압 정상 |
| 키트에 들어 있던 SD 카드에 Wi-Fi·SSH 설정이 없음 | 제조사 이미지에는 집 Wi-Fi 정보가 없다 | Raspberry Pi Imager 로 새로 쓰면서 Wi-Fi·사용자 설정 (제조사 이미지는 지워짐) |
| Imager 로 썼는데 SSH 접속이 안 됨 | Imager 에서 **SSH 대신 Raspberry Pi Connect 만** 켬 (둘은 다른 기능) | SD 카드 `user-data` 에 `ssh_pwauth: true` + `systemctl enable --now ssh`, `meta-data` 의 instance-id 를 바꿔 다음 부팅 때 설정 재적용 |
| 같은 Wi-Fi 인데 라즈베리파이를 못 찾음 | 라즈베리파이 5 는 새 제조사 MAC 주소(`98:fe:54…`)라 목록에서 라즈베리파이로 안 보였고, Windows 에서 `호스트이름.local` 이 안 풀림 | 공유기 DNS 이름(`호스트이름` 만) 또는 22번 포트가 열린 기기로 찾기 |
| SSH 할 때마다 비밀번호 | | 노트북에서 SSH 키 생성 후 라즈베리파이 `~/.ssh/authorized_keys` 에 등록 |
| I2C 장치(`/dev/i2c-1`) 없음 | 새 OS 는 I2C 가 꺼져 있음 | `sudo raspi-config nonint do_i2c 0` 후 **라즈베리파이** 재부팅 |
| `i2cdetect: command not found` | `/usr/sbin` 이 일반 사용자 PATH 에 없음 | `/usr/sbin/i2cdetect -y 1` |
| `sudo` 가 비밀번호를 물음 | Imager 로 만든 사용자는 sudo 에 비밀번호 필요 | 설정 변경은 사람이 직접 비밀번호 입력 |
| "재부팅" 이 어느 장치인지 헷갈림 | | 항상 "라즈베리파이 재부팅" 처럼 장치 이름을 붙인다 |
| 메카넘 바퀴 앞뒤를 바꿔 끼워도 겉보기엔 이상 없음 | 앞뒤·회전은 정상, **옆 이동만** 틀어짐 | 위에서 봤을 때 롤러가 X자인지 확인, `hw_test.py move` 로 옆 이동 점검 |
