from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import pandas as pd
import pickle
from sklearn.linear_model import LinearRegression
from typing import List, Optional
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins 
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
db = client["LaptopPriceDB"]
dataset_collection = db["LaptopPrices"]
model_collection = db["models"] 

# Static files and templates setup
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="templates")

# API endpoint to load dataset from MongoDB
@app.get("/load-dataset")
def load_dataset():
    try:
        cursor = dataset_collection.find({}, {"_id": 0})  # Exclude MongoDB's "_id"
        dataset = list(cursor)
        df = pd.DataFrame(dataset)
        return {"columns": list(df.columns), "data": df.head().to_dict("records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading dataset: {e}")

# Helper function to load the model and feature columns
def load_model_and_features():
    try:
        # Load the model
        model_doc = model_collection.find_one({"model_name": "Linear_Regression_LaptopPrice"})
        if not model_doc:
            raise ValueError("Model not found in the database.")
        
        model = pickle.loads(model_doc['model_binary'])
        print("Model loaded successfully.")  # Debugging print
        
        # Load feature columns
        features_doc = model_collection.find_one({"model_name": "LaptopPrice_Features"})
        if not features_doc:
            raise ValueError("Features not found in the database.")
        
        features = pickle.loads(features_doc['features_binary'])
        print("Feature columns loaded successfully.")  # Debugging print
        
        return model, features

    except Exception as e:
        print(f"Error loading model or features: {e}")
        raise e

# Load the model and features at startup
model, features = None, None
try:
    model, features = load_model_and_features()
except Exception as e:
    print(f"Error loading model or features: {e}")

# Pydantic model for prediction requests 
class PredictionRequest(BaseModel):
    Company: str
    TypeName: str
    Inches: float
    ScreenResolution: str
    Cpu: str
    Ram: int
    Memory: str
    Gpu: str
    OpSys: str
    Weight: float

@app.post("/predict/")
async def predict(request: PredictionRequest):
    if not model or features.empty:
        raise HTTPException(status_code=500, detail="Model or features not loaded.")
    
    try:
        # Transform input data
        input_data = pd.DataFrame([request.dict()])
        
        # Ensure all features are in the correct format
        input_data['Ram'] = input_data['Ram'].apply(lambda x: int(x.replace('GB', '')) if isinstance(x, str) else x)
        input_data['Weight'] = input_data['Weight'].apply(lambda x: float(x.replace('kg', '')) if isinstance(x, str) else x)
        
        # One-hot encoding (adjust this based on how you've set up your features)
        input_data = pd.get_dummies(input_data, columns=input_data.select_dtypes(include='object').columns, drop_first=True)

        # Make sure the input data matches the model's expected input shape
        input_data = input_data.reindex(columns=features, fill_value=0)

        # Make predictions
        predictions = model.predict(input_data)
        return {"predictions": predictions.tolist()}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")


# Dynamic Home Page (Frontend Form)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Run the app with uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
