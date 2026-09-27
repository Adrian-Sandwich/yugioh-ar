"""Identity reconciliation must reject conflicting CIDs and effect-only matches."""
from copy import deepcopy
from curated_registry import evaluate_pair

a={'cardType':'spell','passwords':['00123456'],'externalIDs':{'dbID':1},'text':{'en':{'name':'Example (card)','effect':'Draw 2 cards.'}}}
b=deepcopy(a);b['text']['en']['name']='Example'
assert evaluate_pair(a,b)[0]=='accepted'
b['externalIDs']['dbID']=2
assert evaluate_pair(a,b)[0]=='conflict'
b['externalIDs']={}
assert evaluate_pair(a,b)[0]=='accepted'
b['text']['en']['name']='Different card'
assert evaluate_pair(a,b)[0]=='review'
b['externalIDs']['dbID']=1;b['text']['en']['effect']='Draw 3 cards.'
assert evaluate_pair(a,b)[0]=='review'
b=deepcopy(a);b['passwords']=['99123456']
assert evaluate_pair(a,b)[0]=='review'
b=deepcopy(a);b['cardType']='trap'
assert evaluate_pair(a,b)[0]=='review'
print('PASS: shared serial is insufficient; CID, name, type and effect evidence gates')
