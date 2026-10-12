"""Input checks shared by Coding and AgentRun. No automatic material correction."""
import stat
from pathlib import Path
import app
import statistical_checks


def is_link(path):
    """Reject symlinks and Windows junctions before reading any user input."""
    try:
        info=path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(info,'st_file_attributes',0) &
                                    getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))


def read_text(folder,name,default='',limit=2000):
    path=folder/name
    if is_link(path):raise ValueError(name+' 不允许使用链接。')
    if not path.exists():return default
    if not path.is_file() or path.stat().st_size>limit*4:raise ValueError(name+' 超出范围。')
    value=path.read_text(encoding='utf-8-sig').strip()
    if len(value)>limit:raise ValueError(name+' 超出范围。')
    return value


def validate_inputs(folder):
    folder=Path(folder);materials=folder/'Materials'
    if is_link(folder) or is_link(materials):raise ValueError('输入目录不允许使用链接。')
    if not materials.is_dir():raise ValueError('缺少论文材料文件夹。')
    allowed={'Materials','Profile.txt','Checks.txt','StudyNote.txt','Reference.txt'}
    if any(p.name not in allowed for p in folder.iterdir()):
        raise ValueError('输入目录含未声明的文件，请仅保留材料和约定参数。')
    paths=sorted(materials.iterdir())
    if not 1<=len(paths)<=app.MAX_FILES:raise ValueError('每篇须提供 1 至 20 份材料。')
    if any(is_link(p) or not p.is_file() or p.stat().st_size>app.MAX_UPLOAD_BYTES for p in paths):
        raise ValueError('不接受嵌套目录、链接或超过 20 MB 的文件。')
    if sum(p.stat().st_size for p in paths)>app.MAX_BATCH_BYTES:raise ValueError('材料合计超过 100 MB。')
    profile=read_text(folder,'Profile.txt','review',40)
    checks=statistical_checks.selections([line.strip() for line in read_text(folder,'Checks.txt','',2000).splitlines() if line.strip()])
    note=read_text(folder,'StudyNote.txt','',2000)
    reference=read_text(folder,'Reference.txt','',2048)
    if reference:raise ValueError('公开材料请先在工作台确认并加入材料；批处理不自动下载未确认链接。')
    uploads=[(path.name,path.read_bytes()) for path in paths]
    try:
        app.validate_batch(uploads,profile)
    except app.DemoError as exc:
        raise ValueError(str(exc)) from None
    return uploads,profile,checks,note
