import urllib.request
import json
import urllib.error

def test():
    req = urllib.request.Request(
        'http://127.0.0.1:8000/api/audit/report/creator_2bd2720a1e8a',
        headers={'Cookie': 'session_token=WSwFok8auq90UMPmSWFzq1bJC1X9TcyaYwlvAN0m7mo'}
    )
    try:
        res = urllib.request.urlopen(req, timeout=5)
        print("STATUS:", res.getcode())
        print("BODY:", res.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTP ERROR:", e.code)
        print("ERROR BODY:", e.read().decode())
    except Exception as e:
        print("ERROR:", str(e))

if __name__ == "__main__":
    test()
