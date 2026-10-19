"""L0/D1-D3/M2B: write handmade or header-only CSV sources, without real data or answers."""
import csv
import gzip


HEADERS = {
    'hosp/patients': ('subject_id','gender','anchor_age','anchor_year','anchor_year_group','dod'),
    'hosp/admissions': ('subject_id','hadm_id','admittime','dischtime','deathtime','admission_type',
        'admit_provider_id','admission_location','discharge_location','insurance','language',
        'marital_status','race','edregtime','edouttime','hospital_expire_flag'),
    'hosp/diagnoses_icd': ('subject_id','hadm_id','seq_num','icd_code','icd_version'),
    'hosp/omr': ('subject_id','chartdate','seq_num','result_name','result_value'),
    'icu/chartevents': ('subject_id','hadm_id','stay_id','caregiver_id','charttime','storetime',
        'itemid','value','valuenum','valueuom','warning'),
}


def write_sources(folder, rows=None):
    rows = rows or {}
    for table, header in HEADERS.items():
        path = folder/(table+'.csv.gz')
        path.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(path,'wt',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=header)
            writer.writeheader()
            writer.writerows(rows.get(table,()))
    return folder
