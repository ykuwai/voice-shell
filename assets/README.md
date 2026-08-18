# アイコン

`material-sprite.svg` は Material Symbols (Rounded) から必要な字形だけを取り出して
1枚にまとめたもの。Apache License 2.0。

出どころ: https://github.com/google/material-design-icons
`symbols/web/<name>/materialsymbolsrounded/<name>_24px.svg`（塗りは `<name>_fill1_24px.svg`）

## なぜ手描きをやめたか

以前は SVG のパスを手で書いた自作セットだった。並べたときに大きさと重心がばらつく。
アイコンセットは、線の端点や角の丸み、丸い形を四角い形より少し大きく描くといった
光学補正を全字形で統一している。手で1つずつ描くとそこが揃わない。

## 使い方

30 字形 × 輪郭／塗りの 2 種類。**選択中は塗り、それ以外は輪郭**という規則に使う。

```html
<svg class="ic"><use href="#i-mic"/></svg>        <!-- 輪郭 -->
<svg class="ic"><use href="#i-mic-fill"/></svg>   <!-- 塗り -->
```

**Material Symbols は塗りのパスで描かれている**（線ではない）。CSS は
`fill:currentColor; stroke:none` にする。以前の自作セットは線で描いていたので、
`stroke-width` を指定していた箇所は外すこと。

viewBox は `0 -960 960 960`。24px 系のグリッドと原点が違うので、既存の 24 グリッド用の
指定をそのまま流用しない。

## 入っている字形

check add delete download upload content_copy swap_horiz mic_off tune mic timer
notes visibility palette book_2 list globe language picture_in_picture_alt
auto_awesome pause play_arrow power_settings_new settings arrow_back bolt edit
send close volume_up

`picture_in_picture_alt` は「手前に浮かせる」用（タブが重なった形）。
