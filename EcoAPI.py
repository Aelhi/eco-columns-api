from fastapi import FastAPI
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import string
from gspread.exceptions import NoValidUrlKeyFound, APIError


cred_path = ("D:\Code\Eco Column\ecoServiceAccount.json") # Fix to use environment var

cred = credentials.Certificate(cred_path)
app = firebase_admin.initialize_app(cred)
db = firestore.client()

scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("D:\Code\Eco Column\credentials.json", scopes=scopes) # Export from project
client = gspread.authorize(creds)

app = FastAPI()


class Link(BaseModel):
    sheet_link: str


@app.get("/yearavg/{year}/{filter}")
def get_year_averages(year: str, filter: str):
    """
    Checks a document reference for existence and fetches the datapoint averages if it exists

    :param str year: the year of the datapoint in question
    :param str filter: the plant filter for average values

    :return dict or str: dictionary of document datapoint or datapoint does not exist
    """
    doc = db.collection("Averages").document(year).get()
    if doc.exists:
        doc = doc.to_dict()
        doc_copy = doc.copy()
        for key in doc_copy:
            for i in range(5):
                if filter[i] != doc_copy[key][15][i] and filter[i] != "*": # Iterates through every datapoint and removes from return if the filter does not apply
                    del doc[key]
                    break
        if len(doc) == 0:
            return {"Error" : ["No matching datapoints."]}
        else:
            return doc
    else:
        return {"Error" : ["Datapoints for " + year + " do not exist."]}


@app.get("/groupdata/{year}/{period}/{group}")
def get_group_data(year: str, period: int, group: int):
    """
    Checks a document reference for existence and fetches the datapoint if it exists

    :param str year: the year of the datapoint in question
    :param int group: the group of the datapoint in question
    :param in period: the period of the datapoint in question

    :return dict or str: dictionary of document datapoint or datapoint does not exist
    """
    doc = db.collection(year).document("Period " + str(period) + " Group " + str(group)).get()
    if doc.exists:
        return doc.to_dict()
    else:
        return {"Error" : ["Datapoint " + year + " " + "Period " + str(period) + " " + "Group " + str(group) + " does not exist."]}
    

@app.post("/add/{year}/{period}/{group}/{filter}")
def add_data(year: str, period: int, group: int, filter: str, link: Link):
    """
    Checks a document reference for existence and adds the datapoint if DNE

    :param str year: the year of the datapoint in question
    :param int group: the group of the datapoint in question
    :param int period: the period of the datapoint in question
    :param str filter: the plant filter of the datapoint in question
    :param link Link: the pydantic basemodel containg the link to the google spreadsheet

    :return str: datapoint already exists or datapoint successfully added or error
    """
    try: # In case of invalid gspread url or no access
        worksheet = client.open_by_url(link.sheet_link)
    except NoValidUrlKeyFound:
        return "Invalid spreadsheet URL."
    except PermissionError:
        return "No permission access to spreadsheet given."
    except APIError:
        return "Spreadsheet error."
    sheet_data = worksheet.get_worksheet(0)

    data = {}
    for i in range(15):
        letters = list(string.ascii_uppercase)
        data[sheet_data.acell(f"{letters[i]}1").value] = sheet_data.col_values(i+1)[1:]

    average_list = [f"{period}", f"{group}", ]
    for i in range(3, 16):
        values = sheet_data.col_values(i)[1:]
        values = [float(x) for x in values if x]
        average = sum(values) / len(values) if values else 0
        average_list.append(average)
    average_list.append(filter)
    
    doc = db.collection(year).document("Period " + str(period) + " Group " + str(group)).get()
    avg_doc = db.collection("Averages").document(year).get()
    if doc.exists:
        return "Datapoint " + year + " " + "Period " + str(period) + " " + "Group " + str(group) + " already exists."
    else:
        db.collection(year).document("Period " + str(period) + " Group " + str(group)).set(data)
        if avg_doc.exists:
            db.collection("Averages").document(year).update({"Period " + str(period) + " Group " + str(group): average_list})
        else:
            db.collection("Averages").document(year).set({"Period " + str(period) + " Group " + str(group): average_list})
        return "Datapoint " + year + " " + "Period " + str(period) + " " + "Group " + str(group) + " successfully added."
    

@app.delete("/remove/{year}/{period}/{group}")
def remove_data(year: str, period: int, group: int):
    """
    Checks a document reference for existence and deletes the datapoint if it exists

    :param str year: the year of the datapoint in question
    :param int group: the group of the datapoint in question
    :param int period: the period of the datapoint in question

    :return str: datapoint successfully deleted or datapoint does not exist
    """
    doc = db.collection(year).document("Period " + str(period) + " Group " + str(group)).get()
    if doc.exists:
        db.collection(year).document("Period " + str(period) + " Group " + str(group)).delete()
        averages_doc_ref = db.collection("Averages").document(year)
        averages_doc_ref.update({"Period " + str(period) + " Group " + str(group): firestore.DELETE_FIELD})
        averages_doc = averages_doc_ref.get()
        if averages_doc.exists:
            doc_data = averages_doc.to_dict()
            if not doc_data:
                averages_doc_ref.delete()
        return "Datapoint " + year + " " + "Period " + str(period) + " " + "Group " + str(group) + " successfully deleted."
    else:
        return "Datapoint " + year + " " + "Period " + str(period) + " " + "Group " + str(group) + " does not exist."