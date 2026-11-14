"""Keep incomplete transport requests in clarification; Agent writes questions."""
from repair6.clarification_validation import destination_missing

def install(state_class):
 original=state_class._clarification_command
 def command(self,name,args,request_id,digest):
  if name=='robot_answer_clarification'and destination_missing(args.get('instruction')):
   raise ValueError('clarification_missing_destination: the object answer does not supply a destination. Keep this request pending; submit a model-written follow-up question with the same current user answer. Do not execute or guess a familiar destination.')
  return original(self,name,args,request_id,digest)
 state_class._clarification_command=command
