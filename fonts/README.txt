把中文字体文件放到这个文件夹后，程序会自动使用。

推荐：
  NotoSansCJK-Bold.ttc / NotoSansCJK-Regular.ttc
  或 NotoSansSC-Bold.otf / NotoSansSC-Regular.otf

Windows 用户通常不必放字体，系统自带的微软雅黑（C:\Windows\Fonts\msyh.ttc）会被自动找到。
也可以在运行时指定：

  python make.py --topic 护手霜 --font C:\Windows\Fonts\msyh.ttc
