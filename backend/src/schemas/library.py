from pydantic import BaseModel
class LibraryOutput(BaseModel):
    id:int
    code:str
    name:str
    description:str
    wavelengths:list[float]
    source:str
    endmember_count:int
    sample_count:int
    contamination_group_count:int=0
    supported:bool
    condition_number:float|None
    reason:str
