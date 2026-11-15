"""Noninteractive versioned GAM interface; interactive main remains available."""
import argparse,contextlib,hashlib,json,os,shutil,sys,tempfile
from pathlib import Path

def write(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.gam-')
    with os.fdopen(fd,'w') as f:
        os.fchmod(f.fileno(),0o600);json.dump(data,f);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def execute(source, output):
    from application.app_service import GameArchiveService
    from config.settings import Settings
    from history.storage import HistoryStorage
    class PreserveService(GameArchiveService):
        def _cleanup_successful_run(self,*a,**kw): return []
    source=Path(source); output=Path(output)
    if source.is_symlink() or not source.exists(): raise ValueError('unsafe_input')
    if output.exists() or output.is_symlink(): raise ValueError('output_exists_review_required')
    output.mkdir(parents=True,mode=0o700); (output/'.gam-owned').write_text('v1\n')
    work=output/'input';work.mkdir()
    candidates=[source] if source.is_file() else list(source.iterdir())
    if not candidates: raise ValueError('empty_input')
    for p in candidates:
        if p.is_symlink() or not p.is_file(): raise ValueError('input_must_be_flat_files')
        if shutil.disk_usage(output).free < p.stat().st_size+64*1024**2: raise ValueError('insufficient_disk')
        shutil.copy2(p,work/p.name)
    settings=Settings(seven_zip_path=Path(os.environ.get('SEVEN_ZIP') or shutil.which('7z') or shutil.which('7zz') or shutil.which('7za') or '7z'),
        delete_archives=False,delete_empty_folders=False,save_passwords=False,auto_try_password=False,
        max_password_attempts=1,max_recursive_depth=12,max_archive_tasks=100,max_initial_archive_tasks=100,
        max_total_extracted_size_mb=min(4096,max(64,int(shutil.disk_usage(output).free//(2*1024**2)))))
    service=PreserveService(settings=settings,history_storage=HistoryStorage(output/'history.json'),log_directory=output/'logs')
    report=service.execute_task(work,process_all_inputs=True,content_selection_callback=lambda units:list(range(len(units))))
    if report.failed_count or report.success_count<1 or report.delivery_status!='DELIVERED':
        codes=sorted({x.error_type for x in report.failure_details})
        return dict(schema_version=1,status='failed',code='extraction_or_delivery_failed',failure_types=codes,files=[])
    files=[]
    for root in report.output_paths:
        root=Path(root)
        for p in ([root] if root.is_file() else root.rglob('*')):
            if p.is_symlink() or not p.resolve().is_relative_to(output.resolve()): raise ValueError('unsafe_output')
            if p.is_file(): files.append(str(p.resolve()))
    if not files: raise ValueError('empty_delivery')
    return dict(schema_version=1,status='success',code='verified_extraction',files=sorted(set(files)),source_retained=True)

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--result',required=True)
    a=p.parse_args(argv);os.umask(0o077)
    def digest(p):
        h=hashlib.sha256()
        with Path(p).open('rb') as f:
            for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
        return h.hexdigest()
    try:
        source=Path(a.input)
        inputs=[source] if source.is_file() else sorted(source.iterdir())
        if source.is_symlink() or any(p.is_symlink() or not p.is_file() for p in inputs):raise ValueError('unsafe_input')
        request=dict(input=str(source.resolve()),output=str(Path(a.output).absolute()),files=[dict(name=p.name,sha256=digest(p)) for p in inputs])
        old=json.loads(Path(a.result).read_text()) if Path(a.result).is_file() else {}
        if old.get('request')==request and old.get('status')=='success':
            if not old.get('manifest') or any(not Path(m['path']).is_file() or Path(m['path']).is_symlink() or digest(m['path'])!=m['sha256'] for m in old['manifest']):raise ValueError('output_changed')
            d=old
        else:
            with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
                d=execute(a.input,a.output)
            d['request']=request
            if d['status']=='success':d['manifest']=[dict(path=f,sha256=digest(f),size=Path(f).stat().st_size) for f in d['files']]
    except Exception as e: d=dict(schema_version=1,status='failed',code='gam_error',error_type=type(e).__name__,files=[])
    write(a.result,d);print(json.dumps(d));return 0 if d['status']=='success' else 1

if __name__=='__main__': raise SystemExit(main())
