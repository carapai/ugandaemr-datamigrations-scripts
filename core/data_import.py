import csv
import re
import string
import uuid
from database import Database
from datetime import datetime
from operator import itemgetter
from itertools import groupby

from sql_queries import *

from difflib import SequenceMatcher

db = Database()

today = datetime.now().date().strftime('%Y-%m-%d %H:%M:%S')

visit_concepts = {
    1: '162993',
    2: '162994',
    3: '162995',
    4: '162996',
    5: '162997',
    6: '162998',
    7: '162999',
    8: '163000',
    9: '163001',
    10: '163002',
    11: '163018',
    12: '163019',
    13: '163020',
    14: '163021',
    15: '163022'
}


def create_uuid():
    return str(uuid.uuid4())


def read(file_name):
    l = []
    with open(file_name, 'rb') as csv_file:
        rows = csv.reader(csv_file, delimiter=',')
        for row in rows:
            l.append(row)
    return l


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def search_list(l, val):
    percentages = [(s, similar(val, s)) for s in l]

    percentages.sort(key=lambda tup: tup[1])

    return percentages[-1][0]


def group_data(by_column, data):
    data.sort(key=itemgetter(by_column))
    return groupby(data, itemgetter(by_column))


def transform_list(data):
    transformed_variables = {}
    printable = set(string.printable)

    for variable in data:
        concept = variable[0].partition('(')[-1].rpartition(')')[0]
        answer = filter(lambda x: x in printable, variable[1])
        answer = answer.replace('->', '')

        if concept not in transformed_variables and concept != '':
            transformed_variables[concept] = [answer]
        elif concept in transformed_variables and concept != '':
            l = transformed_variables[concept]
            l.append(answer)
            transformed_variables[concept] = l

    return transformed_variables


def map_to_ugandaemr(dictionary, column, concept, group_no='', group_concept='', answer_dict={}, many=False,
                     separator_for_many=',', converter=None):
    if column is not None:
        dictionary[column] = {
            'concept': concept, 'group_no': group_no, 'group_concept': group_concept, 'answers': answer_dict,
            'many': many,
            'separator_for_many': separator_for_many, 'converter': converter
        }
    return dictionary


def find(lst, value1, value2, value3):
    for i, dic in enumerate(lst):
        if dic['group_no'] == value1 and dic['group_concept'] == value2 and dic['patient_id'] == value3:
            return i
    return -1


def construct_obs(data, identifier_column, form_id, visit_column, encounter_type, mapped_dict, concept_answer_map,
                  location_id=2, no_eid_visit_no=False):
    data = group_data(identifier_column, data)
    obs_list = []
    visits = {}
    for elt, items in data:
        # Get a patient using identifier
        identifier = db.query_one("select * from patient_identifier where identifier = '" + elt + "'")
        if identifier:
            patient_id = identifier['patient_id']
            if patient_id:
                for item in items:
                    visit_date = convert_datetime(item[visit_column])
                    # Search Patient with that visit if it already existed
                    if visit_date:
                        visit = db.query_one(
                            "select * from visit where '" + visit_date + "' BETWEEN date_started and date_stopped and "
                                                                         "patient_id = " + str(patient_id)
                        )
                        if visit:
                            visit_id = visit['visit_id']
                        else:
                            # Create a visit
                            visit_id = db.insert(
                                add_visit,
                                {'patient_id': patient_id, 'visit_type_id': '1', 'date_started': visit_date,
                                 'date_stopped': visit_date, 'location_id': '2',
                                 'date_created': visit_date, 'uuid': create_uuid(), 'creator': '1'}
                            )
                    if visit_id and visit_date:
                        # Create encounter
                        encounter_id = db.insert(
                            add_encounter,
                            {'visit_id': visit_id, 'encounter_type': encounter_type, 'patient_id': patient_id,
                             'location_id': '2',
                             'form_id': form_id,
                             'encounter_datetime': visit_date, 'date_created': visit_date, 'uuid': create_uuid(),
                             'creator': '1'}
                        )
                        if encounter_id:
                            # Add provider to encounter
                            # TODO insert providers

                            db.insert(
                                add_encounter_provider,
                                {'encounter_id': encounter_id, 'provider_id': '2', 'encounter_role_id': '1',
                                 'creator': '1',
                                 'date_created': visit_date, 'uuid': create_uuid()}
                            )
                            if no_eid_visit_no:
                                if patient_id not in visits:
                                    visits[patient_id] = [
                                        {
                                            'visit_date': visit_date, 'encounter_id': encounter_id
                                        }
                                    ]
                                elif patient_id in visits:
                                    visits[patient_id].append({
                                        'visit_date': visit_date, 'encounter_id': encounter_id
                                    })
                            for key, val in enumerate(item):
                                x = mapped_dict.get(str(key + 1))
                                if x is not None:
                                    concept_id = x['concept']
                                    converter = x['converter']
                                    group_no = x['group_no']
                                    group_concept = x['group_concept']
                                    concept_answer = concept_answer_map.get(concept_id)
                                    answer_dictionary = x['answers']
                                    separator_for_many = x['separator_for_many']
                                    many = x['many']

                                    if (concept_id and concept_answer and val) or (
                                                no_eid_visit_no and key == visit_column):
                                        group_index = find(obs_list, group_no, group_concept, patient_id)
                                        obs = {
                                            'person_id': patient_id, 'concept_id': concept_id,
                                            'encounter_id': encounter_id, 'obs_datetime': visit_date,
                                            'value_coded': None,
                                            'value_datetime': None, 'value_numeric': None, 'value_text': None,
                                            'obs_group_id': None,
                                            'location_id': location_id,
                                            'date_created': visit_date, 'uuid': create_uuid(),
                                            'creator': '1'
                                        }

                                        if 'Date' in concept_answer and len(concept_answer) == 1:
                                            obs['value_datetime'] = convert_datetime(val)
                                        elif 'Text' in concept_answer and len(concept_answer) == 1:
                                            obs['value_text'] = val
                                            obs['uuid'] = create_uuid()
                                        elif 'Numeric' in concept_answer and len(concept_answer) == 1:
                                            # print val, key + 1
                                            obs['value_numeric'] = val
                                        else:
                                            if not many:
                                                if val.lower() == 'true':
                                                    val = 'Yes'
                                                if val.lower() == 'false':
                                                    val = 'No'
                                                if converter is not None:
                                                    obs['value_coded'] = converter(val)
                                                elif len(answer_dictionary) > 0:
                                                    k = search_list(list(answer_dictionary.keys()), val)
                                                    obs['value_coded'] = answer_dictionary[k]
                                                else:
                                                    k = search_list(concept_answer, val)
                                                    obs['value_coded'] = k.partition('(')[-1].rpartition(')')[0]
                                            elif many:
                                                many_obs = []
                                                answer_list = val.split(separator_for_many)
                                                for answer in answer_list:
                                                    obs_1 = {
                                                        'person_id': patient_id, 'concept_id': concept_id,
                                                        'encounter_id': encounter_id, 'obs_datetime': visit_date,
                                                        'value_coded': None,
                                                        'value_datetime': None, 'value_numeric': None,
                                                        'value_text': None,
                                                        'obs_group_id': None,
                                                        'location_id': location_id,
                                                        'date_created': visit_date, 'uuid': create_uuid(),
                                                        'creator': '1'
                                                    }

                                                    if converter is not None:
                                                        obs_1['value_coded'] = converter(answer)
                                                    elif len(answer_dictionary) > 0:
                                                        k = search_list(list(answer_dictionary.keys()), answer)
                                                        obs_1['value_coded'] = answer_dictionary[k]
                                                    else:
                                                        k = search_list(concept_answer, answer)
                                                        obs_1['value_coded'] = k.partition('(')[-1].rpartition(')')[0]
                                                    many_obs.append(obs_1)
                                                obs = many_obs

                                        if group_index != -1:
                                            if isinstance(obs, list):
                                                obs_list[group_index]['items'].extend(obs)
                                            else:
                                                obs_list[group_index]['items'].append(obs)
                                        else:
                                            if isinstance(obs, list):
                                                obs_list.append({
                                                    'group_no': group_no, 'group_concept': group_concept,
                                                    'patient_id': patient_id,
                                                    'encounter_id': encounter_id, 'visit_date': visit_date, 'items': obs
                                                })
                                            else:
                                                obs_list.append({
                                                    'group_no': group_no, 'group_concept': group_concept,
                                                    'patient_id': patient_id,
                                                    'encounter_id': encounter_id, 'visit_date': visit_date,
                                                    'items': [obs]
                                                })
    for obs in obs_list:
        items = obs['items']
        if obs['group_no'] and obs['group_concept']:
            obs_id = db.insert(add_obs, {
                'person_id': obs['patient_id'], 'concept_id': obs['group_concept'],
                'encounter_id': obs['encounter_id'], 'obs_datetime': obs['visit_date'], 'location_id': location_id,
                'value_coded': None, 'value_datetime': None, 'value_numeric': None, 'value_text': None,
                'obs_group_id': None, 'date_created': obs['visit_date'], 'uuid': create_uuid(), 'creator': '1'
            })
            for item in items:
                item['obs_group_id'] = obs_id

        db.insert_bulk(add_obs, items)

    if visits:
        for key, value in visits.iteritems():
            sorted_date = sorted(value, key=lambda k: k['visit_date'])
            for i, val in enumerate(sorted_date):
                db.insert(add_obs, {
                    'person_id': key, 'concept_id': '162992',
                    'encounter_id': val['encounter_id'], 'obs_datetime': obs['visit_date'], 'location_id': location_id,
                    'value_coded': visit_concepts[i + 1], 'value_datetime': None, 'value_numeric': None,
                    'value_text': None,
                    'obs_group_id': None, 'date_created': obs['visit_date'], 'uuid': create_uuid(), 'creator': '1'
                })

    print 'Obs have been inserted'


def convert_gender(gender):
    if gender.upper() == 'MALE':
        return 'M'
    elif gender.upper() == 'FEMALE':
        return 'F'
    else:
        return gender


def convert_datetime(given_date):
    try:
        d = datetime.strptime(given_date, '%d/%m/%Y').strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            d = datetime.strptime(given_date, '%d-%b-%y').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            d = None
    return d


def register(data, names_column, gender_column, birth_date_column, address_columns, identifier_columns):
    for row in data:
        names = ['', '-', '']
        address = ['Uganda', '', '', '', '', '']
        if isinstance(names_column, int):
            split_name = row[names_column].split()
            if len(split_name) == 1:
                names[0] = split_name[0]
            elif len(split_name) == 2:
                names[0] = split_name[0]
                names[2] = split_name[1]
            elif len(split_name) == 3:
                names[0] = split_name[0]
                names[1] = split_name[1]
                names[2] = split_name[2]
        elif isinstance(names_column, list):
            if len(names_column == 1):
                names[0] = row[names_column[0]]
            elif len(names_column == 2):
                names[0] = row[names_column[0]]
                names[2] = row[names_column[1]]
            elif len(names_column == 3):
                names[0] = row[names_column[0]]
                names[1] = row[names_column[1]]
                names[2] = row[names_column[2]]

        if address_columns[0]:
            address[0] = row[address_columns[0]]
        if address_columns[1]:
            address[1] = row[address_columns[1]]
        if address_columns[2]:
            address[2] = row[address_columns[2]]
        if address_columns[3]:
            address[3] = row[address_columns[3]]
        if address_columns[4]:
            address[4] = row[address_columns[4]]
        if address_columns[5]:
            address[5] = row[address_columns[5]]

        given_name, middle_name, family_name = tuple(names)
        country, district, county, sub_county, parish, village = tuple(address)

        person_id = db.insert(
            add_person,
            {'gender': convert_gender(row[gender_column]), 'birthdate': convert_datetime(row[birth_date_column]),
             'date_created': today,
             'uuid': create_uuid()}
        )
        db.insert(
            add_person_address,
            {'person_id': person_id, 'preferred': '1', 'address3': sub_county, 'address4': parish, 'address5': village,
             'state_province': county, 'country': country, 'date_created': today, 'county_district': district,
             'uuid': create_uuid(), 'creator': '1'}
        )
        db.insert(
            add_person_name,
            {'person_id': person_id, 'preferred': '1', 'given_name': given_name, 'family_name': family_name,
             'middle_name': middle_name, 'date_created': today, 'uuid': create_uuid(), 'creator': '1'}
        )
        db.insert(
            add_patient,
            {'patient_id': person_id, 'date_created': today, 'creator': '1'}
        )

        for key, value in identifier_columns.iteritems():
            db.insert(
                add_patient_identifier,
                {'patient_id': person_id, 'identifier': row[int(key)], 'identifier_type': value, 'preferred': '1',
                 'location_id': '2',
                 'date_created': today, 'uuid': create_uuid(), 'creator': '1'}
            )
    print "Registration of all patients has been completed"


def create_summary_page(eid_art, other_data=None):
    data = group_data(1, eid_art)
    other_data_grouped = group_data(1, other_data)
    for elt, items in data:
        hiv_clinic_number = re.findall('\d+', elt)[0]
        identifier = db.query_one("select * from patient_identifier where identifier = '" + elt + "'")
        if identifier:
            patient_id = identifier['patient_id']
            if patient_id:
                # TODO Search patient if has identifier of 4
                db.insert(
                    add_patient_identifier,
                    {'patient_id': patient_id, 'identifier': hiv_clinic_number, 'identifier_type': 4, 'preferred': '1',
                     'location_id': '2',
                     'date_created': today, 'uuid': create_uuid(), 'creator': '1'}
                )
                final_outcome = db.query_one(
                    "select * from obs where person_id = '" + str(patient_id) + "' AND concept_id = '99428' ")
                final_outcome_date = db.query_one(
                    "select * from obs where person_id = '" + str(patient_id) + "' AND concept_id = '162979' ")

                final_pcr_date = db.query_one(
                    "select * from obs where person_id = '" + str(patient_id) + "' AND concept_id = '99795' ")

                when_enrolled = db.query_one(
                    "select * from obs where person_id = '" + str(patient_id) + "' AND concept_id = '162980' ")

                if when_enrolled:
                    encounter_date = when_enrolled['value_datetime']
                    if encounter_date:
                        visit_date = encounter_date.date().strftime('%Y-%m-%d %H:%M:%S')
                        if final_pcr_date:
                            hiv_confirmed = final_pcr_date['value_datetime'].date().strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            hiv_confirmed = visit_date
                        # Search Patient with that visit if it already existed
                        if visit_date:
                            visit = db.query_one(
                                "select * from visit where '" + visit_date + "' BETWEEN date_started and date_stopped and "
                                                                             "patient_id = " + str(patient_id)
                            )
                            if visit:
                                visit_id = visit['visit_id']
                            else:
                                # Create a visit
                                visit_id = db.insert(
                                    add_visit,
                                    {
                                        'patient_id': patient_id, 'visit_type_id': '1', 'date_started': visit_date,
                                        'date_stopped': visit_date, 'location_id': '2',
                                        'date_created': visit_date, 'uuid': create_uuid(), 'creator': '1'
                                    }
                                )
                        if visit_id and visit_date:
                            encounter_id = db.insert(
                                add_encounter,
                                {
                                    'visit_id': visit_id, 'encounter_type': 14, 'patient_id': patient_id,
                                    'location_id': '2',
                                    'form_id': 18,
                                    'encounter_datetime': visit_date, 'date_created': visit_date, 'uuid': create_uuid(),
                                    'creator': '1'
                                }
                            )
                            if encounter_id:
                                db.insert(
                                    add_encounter_provider,
                                    {
                                        'encounter_id': encounter_id, 'provider_id': '2', 'encounter_role_id': '1',
                                        'creator': '1',
                                        'date_created': visit_date, 'uuid': create_uuid()
                                    }
                                )

                                # Entry point set
                                obs_id = db.insert(add_obs, {
                                    'person_id': patient_id, 'concept_id': '99116',
                                    'encounter_id': encounter_id, 'obs_datetime': visit_date,
                                    'location_id': '2',
                                    'value_coded': None, 'value_datetime': None, 'value_numeric': None,
                                    'value_text': None,
                                    'obs_group_id': None, 'date_created': visit_date, 'uuid': create_uuid(),
                                    'creator': '1'
                                })

                                # Insert entry point
                                db.insert(add_obs, {
                                    'person_id': patient_id, 'concept_id': '90200',
                                    'encounter_id': encounter_id, 'obs_datetime': visit_date,
                                    'value_coded': '99593',
                                    'value_datetime': None, 'value_numeric': None, 'value_text': None,
                                    'obs_group_id': obs_id,
                                    'location_id': 2,
                                    'date_created': visit_date, 'uuid': create_uuid(),
                                    'creator': '1'
                                })

                                # Date confirmed HIV Positive
                                db.insert(add_obs, {
                                    'person_id': patient_id, 'concept_id': '90267',
                                    'encounter_id': encounter_id, 'obs_datetime': visit_date,
                                    'value_coded': None,
                                    'value_datetime': hiv_confirmed, 'value_numeric': None, 'value_text': None,
                                    'obs_group_id': None,
                                    'location_id': 2,
                                    'date_created': visit_date, 'uuid': create_uuid(),
                                    'creator': '1'
                                })

                                # Test Type
                                db.insert(add_obs, {
                                    'person_id': patient_id, 'concept_id': '99080',
                                    'encounter_id': encounter_id, 'obs_datetime': visit_date,
                                    'value_coded': '99080',
                                    'value_datetime': None, 'value_numeric': None, 'value_text': None,
                                    'obs_group_id': None,
                                    'location_id': 2,
                                    'date_created': visit_date, 'uuid': create_uuid(),
                                    'creator': '1'
                                })
                    else:
                        print 'why'
