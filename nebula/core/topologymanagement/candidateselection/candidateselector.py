from abc import ABC, abstractmethod
from typing import Type

class CandidateSelector(ABC):
    
    @abstractmethod 
    def set_config(self, config):
        pass
    
    @abstractmethod 
    def add_candidate(self, candidate):
        pass
    
    @abstractmethod 
    def select_candidates(self):
        pass
    
    @abstractmethod 
    def remove_candidates(self):
        pass
    
    @abstractmethod 
    def any_candidate(self):
        pass
    
def factory_CandidateSelector(topology) -> CandidateSelector:
    from nebula.core.topologymanagement.candidateselection.stdcandidateselector import STDandidateSelector
    from nebula.core.topologymanagement.candidateselection.fccandidateselector import FCCandidateSelector
    from nebula.core.topologymanagement.candidateselection.hetcandidateselector import HETCandidateSelector
    from nebula.core.topologymanagement.candidateselection.ringcandidateselector import RINGCandidateSelector
    
    options = {
        "ring": RINGCandidateSelector,
        "fully": FCCandidateSelector,
        "random": STDandidateSelector,
        "het": HETCandidateSelector,  
    } 
    
    cs = options.get(topology, FCCandidateSelector)
    return cs() 