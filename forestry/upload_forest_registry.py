# -*- coding: utf-8 -*-
"""forest_registry JSONをFirestoreにアップロードするスクリプト"""

import json
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

HERE = Path(__file__).parent
COLLECTION = "forest_registry"

cred = credentials.Certificate(str(HERE / "serviceAccountKey.json"))
firebase_admin.initialize_app(cred)
db = firestore.client()

with open(HERE / "output" / "forest_registry_24.json", encoding="utf-8") as f:
    patches = json.load(f)["patches"]

batch = db.batch()
count = 0
for p in patches:
    doc = db.collection(COLLECTION).document(p["id"])
    data = {
        "name": p["name"],
        "city": p["city"],
        "planningArea": p["planningArea"],
        "species1": p["species1"], "age1": p["age1"],
        "species2": p["species2"], "age2": p["age2"],
        "species3": p["species3"], "age3": p["age3"],
        "volumeM3": p["volumeM3"],
        "areaHa": p["areaHa"],
        "centerLat": p["centerLat"],
        "centerLng": p["centerLng"],
        # アプリ側の他コレクションと同じくGeoPoint(緯度, 経度)の配列
        "areaPolygon": [firestore.GeoPoint(lat, lng) for lat, lng in p["polygon"]],
    }
    batch.set(doc, data)
    count += 1
    if count % 400 == 0:
        batch.commit()
        batch = db.batch()
        print(f"{count}件...")

batch.commit()
print(f"完了: {count}件を {COLLECTION} にアップロードした")
