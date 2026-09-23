<p align="center">
  <img src="images/logo.svg" alt="Voice Shell" width="88">
</p>

<h1 align="center">Voice Shell</h1>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.ja.md">日本語</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.de.md">Deutsch</a> · <a href="README.zh.md">简体中文</a> · 繁體中文 · <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="授權條款">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="最近一次提交">
</p>

<h3 align="center">把想做的事說出來，用聲音操作 Claude Code！</h3>

<p align="center">Voice Shell 是一個 Agent Skill，讓你直接用聲音對 Claude Code 下指令。</p>

<p align="center">
  <img src="images/screen-zh-TW.png" alt="Voice Shell 的畫面，上面有麥克風、傳送模式、傳送對象和正在辨識的文字" width="380">
</p>

## 💡 特色

### 1. 只靠聲音就能操作 Claude Code

不需要按傳送按鈕。說完話 3 秒後，內容就會自動傳給 Claude Code。\
靜音、取消、切換傳送對象，也都能用聲音完成。

### 2. 常用的詞可以加入字典

像「Cloud Code → Claude Code」這樣容易聽錯的詞，可以自動改正。\
人名、公司名稱、服務名稱等等，也都能輕鬆加入。

### 3. 完全免費，用起來也安心

高品質的語音輸入完全免費，沒有任何收費項目。\
筆電可以用瀏覽器的語音辨識，Mac 或高效能的電腦也可以完全在本機處理。

## 📦 安裝設定

### 需要準備的東西

- Claude Code
- Python 3
- Node.js
- Google Chrome

### 安裝

在終端機貼上下面的指令並執行。

```bash
pip install numpy aiohttp "sounddevice>=0.5.6"
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

接著在 Claude Code 裡輸入 `/voice-shell`，從檢查缺少的東西到啟動，都會自動進行。

### 更新

我們會持續加入新功能。請偶爾用下面的指令更新到最新版。

```bash
npx skills update voice-shell -y
```

## 🎙️ 語音辨識怎麼選

語音辨識的方式有三種，請依照電腦的規格來選。\
可以在畫面的設定裡切換。需要安裝設定時，跟 Claude Code 說一聲，它就會幫你處理。

### 1. 筆電就用瀏覽器的語音辨識

不需要任何設定，馬上就能用。\
這是 Chrome 內建的免費語音辨識（Web Speech API）。\
只要 Chrome 有你這個語言的模型，就在本機辨識；沒有的話，聲音會傳送到 Google 的伺服器。現在是哪一種，設定裡會寫出來。

### 2. Mac 就用 Apple 的本機語音辨識

不想讓聲音離開電腦時，就用在本機處理的語音辨識。\
Mac（macOS 26 以上）可以使用 Apple 的語音辨識，耗電少，速度也快。\
只有第一次需要下載語音辨識的模型，會花一點時間。

### 3. 高效能的電腦（Windows / Linux）就用 Faster Whisper

在 Windows 或 Linux 上裝有 NVIDIA GPU 的話，可以用 [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) 在本機處理。\
第一次需要準備環境和下載模型，會花一點時間。

## 🚀 日常使用

在 Claude Code 裡執行 `/voice-shell`，語音模式就會開始。\
想到什麼就說出來，工作就會一步步往前推進。\
設定會自動儲存，從第二次開始就能沿用上次的狀態，馬上使用。

### 1. 在 Claude Code 輸入 `/voice-shell` 啟動

Chrome 會開啟 Voice Shell 的畫面。\
按下「讓這個視窗固定在最上層」，它就會一直顯示在最前面。

### 2. 解除靜音，開始說話

說出口的內容會直接傳給 Claude Code。\
少於 15 個字的短句（像「嗯」「好」）會被當成雜音，不會傳送。最少字數可以在設定裡調整。\
想暫停說話時，說「靜音」就會關閉麥克風。

### 3. 不想傳送時，在最後說「取消這句」

在一句話的最後說「取消這句」，剛才說的內容就不會傳送，直接取消。\
傳送前想稍微修改的話，點一下畫面上的文字，就能用鍵盤修改。

### 4. 可以從多個工作階段呼叫

在多個 Claude Code 裡執行 `/voice-shell`，畫面上方就會依編號排列出來。\
點一下傳送對象，或是用聲音說「第2個」「工作階段2」，就能切換傳送對象。

> [!NOTE]
> **結束語音模式的方法**
>
> 要結束時，跟 Claude Code 說「結束語音模式」，或是輸入 `/voice-shell stop`。

## 📨 傳送模式

用麥克風按鈕旁邊的按鈕，可以切換傳送模式。

- **即時**（平常用這個） → 說出口的內容會直接傳出去。
- **草稿** → 說出口的內容會累積在畫面上。需要的話可以用鍵盤修改，再依自己的步調傳送。

只想修改剛才說的那一句時，在最後說「這句我來改」。會暫時切換成草稿模式，改好再傳送。

## 🗣️ 好用的語音指令

| 語音指令 | 動作 |
|---|---|
| 「靜音」 | 關閉麥克風 |
| 「解除靜音」 | 開啟麥克風。本機語音辨識，以及在這台裝置上辨識的瀏覽器語音辨識，都聽得到。<br>使用一般的瀏覽器語音辨識時，請按畫面上的麥克風開啟 |
| 「第2個」「工作階段2」 | 使用多個工作階段時，說出傳送對象的編號，就能切換傳送對象 |
| 在最後說「取消這句」 | 取消剛才說的內容 |
| 在最後說「這句我來改」 | 暫時切換成草稿模式 |
| 「草稿模式」「即時模式」 | 切換傳送模式 |

> [!TIP]
> 所有語音指令都可以從畫面上的燈泡圖示查看。\
> 也可以自己新增語音指令，或是把用不到的關掉。

### 多台電腦模式

兩台電腦同時使用時，只要說一聲「靜音」，兩台都會靜音。\
打開燈泡圖示，開啟指令清單下方的「多台電腦一起使用」，替每台取個「公司」「家裡」之類的名字，說「公司靜音」時就只有那一台會靜音。

## ✨ 好用的功能和設定

### 1. 可以調整傳送的時機

預設是說完話 3 秒後傳送。想慢慢說、中間多停頓一下的話，也可以改成 5 秒或 10 秒。\
判斷是否說完話的音量門檻，可以用麥克風下方的滑桿調整。周圍比較吵的時候，請調高一點。

### 2. 不相關的話會自動先保留下來

忘了靜音，連續好幾句和 Claude Code 不相關的話被傳過去時，Claude Code 會自動切換到草稿模式，把內容先保留下來。\
說過的內容會留在畫面上，不會就這樣消失。

### 3. 事後也能更改傳送對象

在多個工作階段中使用，不小心傳到別的工作階段時，可以用滑鼠重新選擇傳送對象。

### 4. 拖曳就能加入字典

有聽錯的地方，只要拖曳選取那一段，就能加入字典。\
下次就能正確辨識，非常方便。

## ⌨️ 鍵盤快速鍵

| 按鍵 | 動作 |
|---|---|
| `Shift` + `M` | 開關麥克風 |
| `Shift` + `L` | 切換到即時模式 |
| `Shift` + `H` | 切換到草稿模式 |
| `Shift` + `E` | 只把剛才說的內容暫時切換成草稿模式 |
| `Shift` + `1` 到 `9` | 用編號切換傳送對象 |
| `Shift` + `Backspace` | 刪除未傳送的內容 |
| `Ctrl` + `Enter`（Mac 是 `Cmd` + `Enter`） | 傳送正在修改的內容 |
| `,` | 開啟設定 |
| `.` | 開啟字典 |
| `?` | 開啟快速鍵和語音指令的清單 |

## 📖 給 AI 代理的文件

這些是 Claude Code 等 AI 代理在操作 Voice Shell 時會讀的文件。

- [SKILL.md](../../skills/voice-shell/SKILL.md) 　使用方式與運作流程
- [SETUP.md](../../skills/voice-shell/SETUP.md) 　各種環境的安裝方式，以及卡住時的處理方法

## 📄 授權條款

MIT
