"""Own the complete worker process tree, including Windows venv launcher children."""
import os
import signal
import subprocess


class ProcessJob:
    def __init__(self,command,**kwargs):
        self.job=None
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes as w
            k=ctypes.WinDLL('kernel32',use_last_error=True)
            class Basic(ctypes.Structure):
                _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',w.DWORD),
                          ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',w.DWORD),
                          ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
            class Extended(ctypes.Structure):
                _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('process_memory',ctypes.c_size_t),
                          ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
            self.extended=Extended
            k.CreateJobObjectW.restype=w.HANDLE;k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]
            k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
            k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
            k.TerminateJobObject.argtypes=[w.HANDLE,w.UINT];k.CloseHandle.argtypes=[w.HANDLE]
            k.QueryInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p]
            self.kernel=k;self.job=k.CreateJobObjectW(None,None)
            limits=Extended();limits.basic.flags=0x2000|0x200  # kill-on-close, complete-tree memory bound
            limits.job_memory=3*1024**3
            if not self.job or not k.SetInformationJobObject(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
                error=ctypes.WinError(ctypes.get_last_error());self.close();raise error
            # Assign before the launcher can create a child. Never leave native CAD
            # outside the job because of the usual venv-spawn race.
            try:self.process=subprocess.Popen(command,creationflags=0x08000000|0x4|0x4000,**kwargs)
            except BaseException:self.close();raise
            if not k.AssignProcessToJobObject(self.job,int(self.process._handle)):
                error=ctypes.WinError(ctypes.get_last_error())
                self.process.kill();self.process.wait(timeout=5);self.close();raise error
            nt=ctypes.WinDLL('ntdll');nt.NtResumeProcess.argtypes=[w.HANDLE]
            if nt.NtResumeProcess(int(self.process._handle))!=0:
                self.stop();self.close();raise RuntimeError('Unable to resume isolated CAD worker')
        else:
            self.process=subprocess.Popen(command,start_new_session=True,**kwargs)

    def stop(self):
        if self.job:self.kernel.TerminateJobObject(self.job,1)
        elif self.process.poll() is None:
            try:os.killpg(self.process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        self.process.wait(timeout=5)

    def close(self):
        if self.job:self.kernel.CloseHandle(self.job);self.job=None

    def metrics(self):
        if not self.job:return {}
        import ctypes
        class Accounting(ctypes.Structure):
            _fields_=[('user',ctypes.c_int64),('kernel',ctypes.c_int64),('period_user',ctypes.c_int64),('period_kernel',ctypes.c_int64),
                      ('page_faults',ctypes.c_uint32),('processes',ctypes.c_uint32),('active',ctypes.c_uint32),('terminated',ctypes.c_uint32)]
        result={};account=Accounting();limits=self.extended()
        if self.kernel.QueryInformationJobObject(self.job,1,ctypes.byref(account),ctypes.sizeof(account),None):
            result['cpu_s']=round((account.user+account.kernel)/10_000_000,4)
        if self.kernel.QueryInformationJobObject(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits),None):
            result['peak_memory_mb']=round(limits.peak_job/1024**2,2)
        return result
