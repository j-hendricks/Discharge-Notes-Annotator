import flask
from flask import Flask, render_template, request
import json
from transformers import pipeline
import requests
import time
from xml.etree import ElementTree as ET
from transformers import LukeTokenizer
from transformers import LukeForEntityPairClassification

'''

rsync -av \
    -e "ssh -i ~/clinical-flask.pem" \
    /Users/johnwhendricks/Desktop/ml_bootcamp/medical_dataset_analysis/ \
    ec2-user@ec2-3-239-110-246.compute-1.amazonaws.com:/home/ec2-user/clinical-flask

'''


app = Flask(__name__)

@app.route('/')
def index():
 return flask.render_template('index.html')

def ValuePredictor(text,option):
    print("This is the prediction numpy array:",text)
    text_refined = text.replace('/n','  ').replace('/r','  ')
    if option == 'concept':
        ner_pipeline = pipeline("ner",model='model_scibert_concept_extraction')
    elif option == 'assertion':
        ner_pipeline = pipeline("ner",model='model_sciebert_assertion')
    else:
        raise KeyError
    result = ner_pipeline(text_refined)
    words1 = [text[res['start']:res['end']] for res in result]
    tags = [res['entity'] for res in result]
    starts = [res['start'] for res in result]
    ends = [res['end'] for res in result]
    print(result)
    words = []
    starts2 = []
    ends2 = []
    s = 0
    end = 0
    for i,r in enumerate(result):
        start = r['start']
        end = r['end']
        if i ==0:
            s = start
        if i < len(result) - 1:
            if 'B' == result[i+1]['entity'][0]:
              the_word = text[s:end]
              starts2.append(s)
              ends2.append(end)
              words.append(the_word)
              s = result[i+1]['start']
            
        else:
            if 'B' == r['entity'][0]:
                the_word = text[start:end]
                starts2.append(start)
                ends2.append(end)
                words.append(the_word)
            else:
                the_word = text[s:end]
                starts2.append(s)
                ends2.append(end)
                words.append(the_word)

    # print("Ends:", ends)
       
    pairs = zip(words1,tags,starts,ends)

    pairs2 = zip(words, starts2, ends2)
    
    return [(w1,t,s,e) for w1,t,s,e in pairs],[(w,s,e) for w,s,e in pairs2]

def predict(text, entity_spans, model_path, device="cpu"):
    """Predict on new example"""
    # Load the model
    id2label = {
    0: "No Relationships Found", #O
    1: "Test Reveals Medical Problem", #TeRP
    2: "Medical Problem Indicates Other Medical Problem", #PIP
    3: "Test Conducted to Investigate Medical Problem", #TeCP
    4: "Treatment is Administered for Medical Problem", #TrAP
    5: "Treatment Improves Medical Problem", #TrIP
    6: "Treatment Causes Medical Problem", #TrCP
    7: "Treatment Worsens Medical Problem", #TrWP
    8: "Treatment is not Administered Because of Medical Problem"} #TrNAP

    print("Text:", text)
    print("Spans:",entity_spans)

    model = LukeForEntityPairClassification.from_pretrained(model_path)
    # model.eval()  # Ensure the model is in evaluation mode
    
    # Load the tokenizer
    tokenizer = LukeTokenizer.from_pretrained(model_path)
    
    # Tokenize the input
    inputs = tokenizer(text, entity_spans=entity_spans, return_tensors="pt").to(device)
    
    # Perform inference
    outputs = model(**inputs)
    logits = outputs.logits
    predicted_class_idx = logits.argmax(-1).item()
    return id2label[predicted_class_idx]  

def search_pubmed_articles(query):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    search_url = base_url + "esearch.fcgi"
    fetch_url = base_url + "efetch.fcgi"
    print("Query:", query)
    articles = []
    for q in query:
        print('q:',q)
        # Perform a search query
        search_params = {
            "db": "pubmed",
            "term": q,
            "retmax": 1,  # Number of articles to retrieve
            "retmode": "json"
        }
    
        try:
            response = requests.get(search_url, params=search_params)
    
            search_results = json.loads(response.text)

        except:
            search_results = []
    
        # Extract PMIDs from search results
        try:
            pmids = search_results["esearchresult"]["idlist"]
        except:
            pmids = []
        print(pmids)
        # Fetch article details using PMIDs
        
        counter = 0
        for pmid in pmids:
            if counter > 1:
                break
            fetch_params = {
                "db": "pubmed",
                "id": pmid,
                "retmode": "json"
            }
            fetch_response = requests.get(fetch_url, params=fetch_params)
            article_details = json.loads(fetch_response.text)
            articles.append(article_details)
            counter += 1
            time.sleep(1)
    
    return articles

def get_article_details(articles):
    a_list = []
    for article in articles: 
        a_list.append(get_abstract_from_pmid(article))
    return a_list

def get_abstract_from_pmid(pmid):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml"
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        xml_data = response.text

        # Extracting URL from the XML response
        start_index = xml_data.find('<ArticleId IdType="doi">') + len('<ArticleId IdType="doi">')
        end_index = xml_data.find('</ArticleId>', start_index)
        doi = xml_data[start_index:end_index]

        url = f'https://doi.org/{doi}'
        root = ET.fromstring(response.content)
        title = root.find('.//ArticleTitle').text

        return title, url
    except requests.exceptions.RequestException as e:
        print("Error fetching data:", e)
        return None

 


@app.route('/predict',methods = ['POST'])
def result():

 if request.method == 'POST':

    to_predict_list = request.form.to_dict()

    result = ValuePredictor(to_predict_list['notes'],'concept')
    result2 = ValuePredictor(to_predict_list['notes'],'assertion')

    articles = search_pubmed_articles([r[0] for r in result[1]])
    articles = get_article_details(articles)

    articles = [article for article in articles if article is not None]

    title = [article[0] for article in articles]

    url = [article[1] for article in articles]

    w = [r[0] for r in result[1]]

    t1 = ''
    u1 = ''
    t2 = ''
    u2 = ''
    w1 = ''
    w2 = ''
    w3 = ''
    t3 = ''
    u3 = ''


    if len(title) > 0:
        t1 = title[0]
        u1 = url[0]
        w1 = w[0]
    if len(title) > 1:
        t2 = title[1]
        u2 = url[1]
        w2 = w[1]
    if len(title) > 2:
        t3 = title[2]
        u3 = title[2]
        w3 = w[2]

    
    
    spans = [(r[1],r[2]) for r in result[1]]

    # print('Check:',[r for r in result])

    relations = []

    for span1 in spans:
        for span2 in spans:
            if span1 != span2 and span1[0] < span2[0] and '.' not in to_predict_list['notes'][span1[0]:span2[1]] and len(relations) < 15:
                relation = predict(to_predict_list['notes'],[span1,span2],'./model_relations_scibert')
                relations.append(to_predict_list['notes'][span1[0]:span1[1]])
                relations.append(to_predict_list['notes'][span2[0]:span2[1]])
                relations.append(relation)

    print('Relation:', relations)

    print(title)

    print(url)

    print(relations)


    
    
 return render_template('index.html',prediction=result[0], notes=to_predict_list['notes'].replace('/n',' '), title1 = t1, url1 = u1, title2 = t2, url2 = u2, title3=t3,url3=u3, w1=w1,w2=w2,w3=w3,relation=relations,assertion = result2[0])

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=80)
