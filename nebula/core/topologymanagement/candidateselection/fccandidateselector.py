from nebula.core.topologymanagement.candidateselection.candidateselector import CandidateSelector
from nebula.core.utils.locker import Locker

class FCCandidateSelector(CandidateSelector):
    
    def __init__(self):
        self.candidates = []
        self.candidates_lock = Locker(name="candidates_lock")
        
    def set_config(self, config):
        pass    
    
    def add_candidate(self, candidate):
        self.candidates_lock.acquire()
        self.candidates.append(candidate)
        self.candidates_lock.release()
      
    def select_candidates(self):
        """
            In Fully-Connected topology all candidates should be selected
        """
        #0145
        #listed = ["192.168.51.2:45001", "192.168.51.3:45002", "192.168.51.6:45005", "192.168.51.7:45006"]
        #defined = []
        self.candidates_lock.acquire()
        cdts = self.candidates.copy()
        #for (addr,a,b) in cdts:
        #    if addr in listed:
        #        defined.append((addr,a,b))
        #cdts = defined
        self.candidates_lock.release()
        return cdts
    
    def remove_candidates(self):
        self.candidates_lock.acquire()
        self.candidates = []
        self.candidates_lock.release()

    def any_candidate(self):
        self.candidates_lock.acquire()
        any = True if len(self.candidates) > 0 else False
        self.candidates_lock.release()
        return any