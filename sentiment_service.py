import re
import string
import joblib

model = joblib.load("model_naive_bayes.pkl")
tfidf = joblib.load("tfidf_vectorizer.pkl")


def bersihkan_teks(text):

    text = str(text).lower()

    text = re.sub(
        r"http\S+|www\S+|@\w+|#|\d+",
        "",
        text
    )

    text = text.translate(
        str.maketrans("", "", string.punctuation)
    )

    text = re.sub(r"\s+", " ", text).strip()

    return text


def prediksi_sentimen(list_text):

    clean_texts = [
        bersihkan_teks(text)
        for text in list_text
    ]

    vectors = tfidf.transform(clean_texts)

    predictions = model.predict(vectors)

    return clean_texts, predictions