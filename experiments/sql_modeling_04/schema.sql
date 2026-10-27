-- D1-D7 / ADR0001,0003,0005,0010,0013: isolated handmade experiment, not product migrations.
create or replace table sources (hospital varchar, derived_from varchar);
create or replace table persons (hospital varchar, person_id varchar, omop_person_id integer, measurement_year integer, year_of_birth integer);
create or replace table conditions (hospital varchar, source_row_key varchar, omop_person_id integer, condition_concept_id integer, condition_start_date date, condition_end_date date);
create or replace table visits (hospital varchar, source_row_key varchar, omop_person_id integer, visit_concept_id integer, visit_start_date date, visit_end_date date);
create or replace table measurements (hospital varchar, source_row_key varchar, omop_person_id integer, measurement_concept_id integer, measurement_date date, value_as_number double, unit_concept_id integer);
create or replace table indicator_concepts (concept_set varchar, concept_id integer);
create or replace table as_of_labels (as_of_label varchar, month integer, day integer);

-- Projection adapters: no new clinical meaning or source mapping.
create or replace view condition_occurrence as select omop_person_id as person_id, condition_concept_id, condition_start_date, condition_end_date from conditions;
create or replace view visit_occurrence as select omop_person_id as person_id, visit_concept_id, visit_start_date, visit_end_date from visits;
create or replace view measurement as select omop_person_id as person_id, measurement_concept_id, measurement_date, value_as_number, unit_concept_id from measurements;
create or replace view periods as
select p.hospital, labels.as_of_label, p.person_id, p.omop_person_id,
       make_date(p.measurement_year, 1, 1) as measurement_start_day,
       make_date(p.measurement_year, 6, 30) as hypertension_cutoff_day,
       make_date(p.measurement_year, labels.month, labels.day) as as_of,
       least(make_date(p.measurement_year, labels.month, labels.day), make_date(p.measurement_year, 12, 31)) as period_end_day,
       p.measurement_year - p.year_of_birth as age_at_year_end
from persons p cross join as_of_labels labels;

create or replace view dim_source as select * from sources;
create or replace view dim_person as select * from persons;
create or replace view dim_date as
select distinct as_of, year(as_of)::integer as year, month(as_of)::integer as month, day(as_of)::integer as day from periods;
create or replace view source_as_of_scope as
select distinct p.hospital, p.as_of, p.as_of_label, people.measurement_year
from periods p join persons people using (hospital, person_id);
create or replace view source_label_scope as select distinct hospital, as_of_label from periods;
