from pathlib import Path
import os
root=Path(SPECPATH).parent
tool=Path(os.environ.get('IFS_MODEL_VETTING_PATH',root.parent/'ifs-model-vetting')).resolve()
a=Analysis([str(root/'desktop_launcher.py')],pathex=[str(root),str(tool)],binaries=[],
    datas=[(str(tool/'index.html'),'.'),(str(tool/'audit.js'),'.'),
           (str(root/'shell.html'),'.'),(str(root/'shell.js'),'.'),(str(root/'shell.css'),'.'),
           (str(root/'decoder-runtime'),'decoder-runtime')],
    hiddenimports=['app','diagnostics','folder_picker','tkinter','tkinter.filedialog','tkinter.messagebox'],
    excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='IFsCompanionEngine',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='IFsCompanionEngine')
