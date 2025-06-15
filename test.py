import requests
import time

BASE_URL = "http://w.vasys.ru:5000"  # Замените на ваш URL, если он отличается
API_KEY = "JraTjhlxKJef455XP9FOHm5uRBoHFsD33p78WXBOUWQ"  # Замените на ваш API ключ

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def test_get_video():
    url = f"{BASE_URL}/get_video"
    data = {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "quality": "720p"
    }
    response = requests.post(url, json=data, headers=headers)
    print("Get Video Response:", response.json())
    return response.json().get("task_id")

def test_get_audio():
    url = f"{BASE_URL}/get_audio"
    data = {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    }
    response = requests.post(url, json=data, headers=headers)
    print("Get Audio Response:", response.json())
    return response.json().get("task_id")

def test_get_live():
    url = f"{BASE_URL}/get_live_video"
    data = {
        "url": "https://www.youtube.com/watch?v=-WzzHOjuMRI",  # Замените на URL реального стрима
        "start": 0,
        "duration": 5*60,
        "quality": "best"
    }
    response = requests.post(url, json=data, headers=headers)
    print("Get Live Response:", response.json())
    return response.json().get("task_id")

def check_status(task_id):
    url = f"{BASE_URL}/status/{task_id}"
    response = requests.get(url, headers=headers)
    print(f"Status for task {task_id}:", response.json())

def main():
    # # Тест get_video
    # video_task_id = test_get_video()
    
    # # Тест get_audio
    # audio_task_id = test_get_audio()
    
    # Тест get_live
    live_task_id = test_get_live()
    
    # Ждем немного и проверяем статусы
    time.sleep(10)
    
    # check_status(video_task_id)
    # check_status(audio_task_id)
    check_status(live_task_id)

if __name__ == "__main__":
    main()