from ds_proc_base import ds_base
import subprocess
from ds_exception import DSException
import time

## @class ds_multiprocess
#  @brief A class that handles parallelization of command execution
#  @details Someone should replace this w/ multiprocessing
class ds_multiprocess(ds_base):

    _proc_v = []
    _cout_v = []
    _cerr_v = []

    def __init__(self,arg=None):

        if arg is None: arg = self.__class__.__name__
        super(ds_multiprocess,self).__init__(arg)

    def execute(self,cmd):
        active_ctr = self.active_count()
        try:
            shell = type(cmd) == type(str())
            p = subprocess.Popen(cmd,shell=shell,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self._proc_v.append(p)
            self._cerr_v.append(None)
            self._cout_v.append(None)
            return (len(self._proc_v)-1,active_ctr+1)
        except Exception:
            self.error('Failed to execute: %s' % cmd)
            return (-1,active_ctr)

    def finished(self,index=None):
        if index is None:
            for p in self._proc_v:
                if p.poll() is None:
                    return False
        elif index < len(self._proc_v):
            return (not self._proc_v[index].poll() is None)        
        else:
            raise DSException('Invalid process index: %d' % index)
        return True

    def poll(self,index):
        return self._proc_v[index].poll()

    def communicate(self,index):
        if self._cout_v[index] is None:

            self._cout_v[index], self._cerr_v[index] = self._proc_v[index].communicate()
            
        return (self._cout_v[index],self._cerr_v[index])

    def kill(self):
        for i in xrange(len(self._proc_v)):
            p = self._proc_v[i]
            if not p.poll() is None: continue
            p.kill()
            slept_time = 0
            while slept_time < 10:
                if not p.poll() is None: break
                time.sleep(0.2)
                slept_time += 0.2
            if p.poll() is None:
                subprocess.call(['kill','-9',str(p.pid)])

    def active_count(self):
        ctr=0
        for p in self._proc_v:
            if p.poll() is None: ctr+=1
        return ctr

        









        