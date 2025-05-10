import json
import random
from faker import Faker

fake = Faker()
random.seed(42)

# Fields to name
name_mappings = {
    "caseNumber": {},
    "hospitalId": {},
    "procedureName": {},
    "primaryNpi": {},
    "fin": {},
    "market": {},
    "ministry": {},
    "speciality": {},
    "npis": {}
}

# Generate a unique, consistent name
def get_or_create(mapping, key, name_func):
    if key not in mapping:
        mapping[key] = name_func()
    return mapping[key]

# Load the files
with open('output_deidentifiedCase.json') as f:
    cases = json.load(f)

with open('output_deidentifiedBlock.json') as f:
    groups = json.load(f)

# Process cases
for case in cases:
    if 'caseNumber' in case:
        case['caseName'] = get_or_create(name_mappings['caseNumber'], case['caseNumber'], fake.word)
    if 'hospitalId' in case:
        case['hospitalName'] = get_or_create(name_mappings['hospitalId'], case['hospitalId'], fake.company)
    if 'fin' in case:
        case['finName'] = get_or_create(name_mappings['fin'], case['fin'], fake.uuid4)

    for proc in case.get('procedures', []):
        if 'procedureName' in proc:
            proc['procedureLabel'] = get_or_create(name_mappings['procedureName'], proc['procedureName'], fake.bs)
        if 'primaryNpi' in proc:
            proc['providerName'] = get_or_create(name_mappings['primaryNpi'], proc['primaryNpi'], fake.name)

# Process groups
for group in groups:
    if 'market' in group:
        group['marketName'] = get_or_create(name_mappings['market'], group['market'], fake.city)
    if 'ministry' in group:
        group['ministryName'] = get_or_create(name_mappings['ministry'], group['ministry'], fake.company)
    if 'speciality' in group:
        group['specialityName'] = get_or_create(name_mappings['speciality'], group['speciality'], fake.job)

    if 'owner' in group:
        for owner in group['owner']:
            if 'npis' in owner:
                owner['providerNames'] = []
                owner['npiNameMap'] = []
                for npi in owner['npis']:
                    name = get_or_create(name_mappings['primaryNpi'], npi, fake.name)
                    owner['providerNames'].append(name)
                    owner['npiNameMap'].append({ "npi": npi, "providerName": name })

# Save outputs
with open('cases_named.json', 'w') as f:
    json.dump(cases, f, indent=2)

with open('groups_named.json', 'w') as f:
    json.dump(groups, f, indent=2)

print("✓ Surrogate names added and saved to cases_named.json and groups_named.json.")
