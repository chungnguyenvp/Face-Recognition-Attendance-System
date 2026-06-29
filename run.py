import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8002, reload=True)



#http://10.33.96.3:8002