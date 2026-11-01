# 云上跑 1 个月（Linux + NapCat 原生）

目标：把这套 NoneBot2 机器人搬到云服务器上，只跑 1 个月。腾讯云、阿里云都适用，命令差别只在登录用户。
协议端不用 Docker，直接在服务器上跑 QQ + NapCat（xvfb 无头），和 Windows 那套逻辑一致，反向 WS 走 `127.0.0.1:8080`。
（目录名沿用 `tencent`，两家命令都在这份里，按表里的「登录用户」换就行。）

> 这台机器的实例信息、进度、已知坑都在 **[SERVER.md](SERVER.md)**，接手前先看那个。

## 0. 买什么

| 项 | 腾讯云 | 阿里云 |
| --- | --- | --- |
| 产品 | 轻量应用服务器 Lighthouse（**不是** CVM） | 轻量应用服务器 SWAS（**不是** ECS） |
| 试用入口 | <https://cloud.tencent.com/act/free/personal> → 个人认证 → 2核2G3M 1个月 | <https://free.aliyun.com/> → 实名 → 能领到 ≥2核2G 就先领 |
| 直接买 | 2核2G / 40G / 3M / 200G 流量，**45 元/月** | 2核2G / 40G / 3M 档，**约 60–80 元/月** |
| 地域 | 上海 / 广州 / 南京 | 杭州 / 上海 / 北京 |
| 镜像 | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS（没有就 22.04） |
| 登录用户 | `ubuntu`，要 `sudo` | `root`，直连 |
| 时长 | 1 个月，**别勾自动续费** | 1 个月，**自动续费默认是开的，必须手动关** |

注意：

- 两家都只卖包年包月，最短 1 个月，正好。
- 阿里云新实例**没有初始密码**，创建后到控制台「重置密码」。
- 40G 盘的套餐两家都选不了 Windows 镜像（要 >40GiB 盘），要 Windows 得 50G 起，价格翻倍，不值。
- 不需要域名、不需要备案——机器人只监听本机，不对外开端口。
- 实名认证是前提，没认证领不到试用。
- 防火墙（阿里云叫「防火墙」，腾讯云也叫「防火墙」）只留 22/80/443，**别放通 6099、8080**。

## 1. 本地打包上传

```powershell
.\deploy\tencent\pack.ps1            # 不带记忆库
.\deploy\tencent\pack.ps1 -IncludeData   # 连 data/bot.db 一起带走
```

提示「cannot be loaded / 没有数字签名」就换这个跑法：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\tencent\pack.ps1
```

产物 `dist\qqbot-deploy.tar.gz`，然后按云选一行：

```powershell
scp .\dist\qqbot-deploy.tar.gz ubuntu@<公网IP>:~/    # 腾讯云
scp .\dist\qqbot-deploy.tar.gz root@<公网IP>:~/      # 阿里云
```

## 2. 服务器上装环境

```bash
ssh ubuntu@<公网IP>        # 阿里云换成 root@<公网IP>
sudo mkdir -p /opt/qqbot
sudo tar -xzf ~/qqbot-deploy.tar.gz -C /opt/qqbot
sudo -i                    # 阿里云本来就是 root，这步可以省
bash /opt/qqbot/deploy/tencent/bootstrap.sh

# Linux 没 NapCat OCR，关掉；看图走 AI_VISION_MODEL
sed -i 's/^AI_IMAGE_OCR=.*/AI_IMAGE_OCR=false/' /opt/qqbot/.env
```

`bootstrap.sh` 干这些事：装系统依赖（xvfb、中文字体、libnss3 等）→ 建 1G swap → 建 `.venv` 装依赖（清华源）→ 调官方安装器装 QQ + NapCat 到 `/root/Napcat`。

GitHub 下载卡住的话，把脚本里 `--github-proxy 0` 换成镜像前缀，例如：

```bash
bash napcat.sh --docker n --cli y --github-proxy https://ghfast.top
```

（第三方加速站，自己判断可信度；直连能过就别用。）

## 3. 首次登录 QQ

```bash
xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox -q <机器人QQ号>
```

- 终端会打印二维码；同时落在 `/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png`
  （路径不对就 `find /root/Napcat -name 'qrcode*.png'`）。
- 终端里扫不方便就下载图片扫：

  ```powershell
  # 腾讯云：root 的文件，先挪到 /tmp 并给权限
  ssh ubuntu@<公网IP> "sudo cp /root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png /tmp/q.png && sudo chmod 644 /tmp/q.png"
  scp ubuntu@<公网IP>:/tmp/q.png .

  # 阿里云：root 直连，一步到位
  scp root@<公网IP>:/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png .
  ```

- 二维码约 2 分钟有效，过期 Ctrl+C 重跑。
- 机房 IP 首登大概率要滑块/短信，用小号，别用主号。
- 登录成功后**先 Ctrl+C 停掉**，交给 systemd 托管（下一步）。

## 4. 配反向 WS

WebUI 只监听本机，用 SSH 隧道进：

```powershell
ssh -L 6099:127.0.0.1:6099 ubuntu@<公网IP>   # 阿里云改成 root@
```

浏览器打开 <http://127.0.0.1:6099/webui>，token 看 NapCat 控制台日志里打印的那串。

进去后「网络配置」新建 **WebSocket 客户端（反向 WS）**：

- URL：`ws://127.0.0.1:8080/onebot/v11/ws`
- Token：`.env` 里的 `ONEBOT_ACCESS_TOKEN`（两边必须一模一样）
- 消息格式：`array`

保存后重启 NapCat。

## 5. 挂 systemd

先看安装器有没有自己建服务：

```bash
systemctl list-units --all | grep -i napcat
```

- 有的话直接用它的，跳到下一步，**别**再装 `napcat.service`（会抢同一个 QQ 进程）。
- 没有就用自带的两个 unit：

```bash
cp /opt/qqbot/deploy/tencent/qqbot.service /etc/systemd/system/
cp /opt/qqbot/deploy/tencent/napcat.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now qqbot napcat
```

日志：

```bash
journalctl -u qqbot -f
journalctl -u napcat -f
```

## 6. 验证

```bash
curl -s 127.0.0.1:8080/healthz
# {"ok":true,"uptime":...,"bots":1}
```

`bots:1` 才说明 NapCat 连上了。然后 QQ 私聊发一句，群里 @ 一下。

## 7. Linux 上和 Windows 不一样的地方

| 项 | 处理 |
| --- | --- |
| `tools/` 里的 win64 NapCat | 不用，Linux 用安装器装的 `/root/Napcat` |
| `scripts/*.ps1`、`start_all.bat` | Linux 用不了，本目录的脚本替代 |
| 图片 OCR | NapCat Linux 没有 `ocr_image`，把 `.env` 的 `AI_IMAGE_OCR=false`；`AI_VISION_MODEL=deepseek-v4.1-flash` 保留，看图走视觉模型 |
| 中文字体 | `fonts-noto-cjk` 已装，日志不会再乱码；`make_stickers.py` 的 `C:/Windows/Fonts/msyhbd.ttc` 用不上，表情包 `assets/` 里已经有了，不影响运行 |
| 内存 | 2G 紧，脚本加了 1G swap；`free -m` 看 used 长期 >1.6G 就升 2C4G |

## 8. 到期前

试用 1 个月到期会释放，数据一起没。服务器上：

```bash
# 腾讯云（ubuntu 用户，root 的文件先挪出来）
sudo cp /opt/qqbot/data/bot.db /home/ubuntu/bot.db && sudo chown ubuntu:ubuntu /home/ubuntu/bot.db
sudo cp /opt/qqbot/.env /home/ubuntu/env.bak && sudo chown ubuntu:ubuntu /home/ubuntu/env.bak
# 阿里云是 root，不用挪，直接拉 /opt/qqbot 下的
```

```powershell
# 腾讯云
scp ubuntu@<公网IP>:~/bot.db .\data\bot.db
scp ubuntu@<公网IP>:~/env.bak .\.env

# 阿里云
scp root@<公网IP>:/opt/qqbot/data/bot.db .\data\bot.db
scp root@<公网IP>:/opt/qqbot/.env .\.env
```

想续就控制台续费（两家续费都有折扣）；不想续，先把 `bot.db` 拉回来，回本机接着跑。

## 9. 常见坑

| 现象 | 原因 |
| --- | --- |
| `Bot connected` 一直不出现 | token 不一致（403），或反向 WS 的 URL 写错端口 |
| 扫码后掉线 | 机房 IP 风控，重扫；还不行换小号 |
| `pip install` 超时 | 用 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| GitHub 下载 QQ/NapCat 失败 | 挂 `--github-proxy`，或手动下 `.deb` + `NapCat.Shell.zip` 走离线安装 |
| 6099 打不开 | 正常，走 SSH 隧道；别在防火墙放通它 |
| `database is locked` | 起了两个 `bot.py`，`systemctl status qqbot` 看一眼 |
| 阿里云到期后自动扣了一个月 | 购买页「自动续费」默认勾着，没关 |
| 阿里云 SSH 连不上/密码错 | 新实例没有初始密码，先控制台「重置密码」 |
