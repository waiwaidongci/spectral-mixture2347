from pydantic import BaseModel,Field
class GroupInput(BaseModel):
    code:str=Field(min_length=2,max_length=40)
    name:str=Field(min_length=2,max_length=120)
    note:str=Field(default="",max_length=1500)
    member_sample_ids:list[int]=Field(min_length=2,max_length=6)
    matrix:list[list[float]]
    registration_note:str=Field(default="",max_length=1500)
class RegistrationInput(BaseModel):
    member_sample_ids:list[int]=Field(min_length=2,max_length=6)
    matrix:list[list[float]]
    note:str=Field(default="",max_length=1500)
