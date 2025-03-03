from nebula.core.situationalawareness.awareness.satraining.trainingpolicy.trainingpolicy import TrainingPolicy

class BPSTrainingPolicy(TrainingPolicy):
    
    def __init__(self, config=None):
        pass
    
    async def init(self, config):
        pass    

    async def update_neighbors(self, node, remove=False):
        pass
    
    async def evaluate(self):
        return None