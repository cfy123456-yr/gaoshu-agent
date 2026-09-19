# PythonAnywhere Deployment

PythonAnywhere provides a free, long-running web app without requiring a
credit card or a local GitHub connection.

## 1. Create a free account

1. Open: <https://www.pythonanywhere.com/registration/register/beginner/>
2. Create a free Beginner account.
3. Remember your PythonAnywhere username.

## 2. Clone the project in a Bash console

Open **Consoles -> Bash** and replace `YOUR_USERNAME` with your PythonAnywhere
username:

```bash
cd "$HOME"
git clone https://github.com/cfy123456-yr/gaoshu-agent.git
cd "$HOME/gaoshu-agent"
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If Python 3.13 is unavailable, use `python3.12` instead.

## 3. Create the web app

1. Open **Web -> Add a new web app**.
2. Choose **Manual configuration**.
3. Choose the same Python version used above.
4. Set **Source code** to `/home/YOUR_USERNAME/gaoshu-agent`.
5. Set **Virtualenv** to `/home/YOUR_USERNAME/gaoshu-agent/.venv`.

## 4. Replace the WSGI file

Open the WSGI configuration file shown on the Web page. Replace its entire
contents with `deploy/pythonanywhere_wsgi.py`. The file resolves the project
from the current user's home directory and uses the synchronous Flask WSGI
entry point in `deploy/wsgi_app.py`.

Save the file, then click **Reload**.

## 5. Verify

Open:

```text
https://YOUR_USERNAME.pythonanywhere.com/health
```

The response should contain `"status":"ok"`.

The public API base URL is:

```text
https://YOUR_USERNAME.pythonanywhere.com
```
