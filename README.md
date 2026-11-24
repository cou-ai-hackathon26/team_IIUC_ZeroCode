# Roadmind

Traffic lights that think about people.

We are team IIUC_ZeroCode from International Islamic University Chittagong, and we made Roadmind for the CoU AI Hackathon 2026.

## The idea

At most junctions in our cities the signal either runs on a fixed timer or doesn't work at all, so the traffic police control it by hand. A bus full of people can sit at a red light while the green goes to a road with two cars. The timer doesn't know the difference.

So we thought, what if the signal looked at how many people are waiting, not how many vehicles?

Roadmind uses the camera that is already at the junction. Our AI finds the vehicles and people on each road, estimates how many people are waiting, and tells the traffic officer in Bangla which road should get more green time. The officer presses Accept or Override:

- **Accept** sends the new timing to the lights straight away
- **Override** lets the officer set his own time and pick a reason
- if the officer does nothing, the lights keep running on their normal timer, like they do now

Roadmind never changes a light on its own. The officer always decides.

## How we count people

The AI can't see inside a bus, and for privacy we don't want it to. So we use the average number of people each vehicle usually carries:

| Vehicle | People (average) |
|---|---|
| bus | 40 |
| leguna | 12 |
| battery rickshaw | 4 |
| CNG | 3 |
| rickshaw | 2 |
| car | 1.5 |
| motorbike | 1.3 |
| truck | 1.2 |
| bicycle | 1 |

These are averages over many vehicles, so 10 cars count as about 15 people. The officer can see and change them under **Assumptions**, because a Dhaka bus is not the same as a bus in a small town.

Example: one bus on Road 1 (about 40 people) and ten motorbikes on Road 2 (about 13 people). Counting vehicles, Road 2 wins. Counting people, Road 1 wins. Roadmind gives the green to Road 1.

## What it does

**Live advice**
- watches the junction video and counts vehicles and people on each road
- finds the roads by itself by watching which way traffic moves for about 20 seconds (road names come from the junction file)
- gives new advice about every cycle, in Bangla and English, with the time it was made
- each advice can be decided only once, then the buttons lock until the next advice
- 🔊 Speak reads the advice out loud in Bangla
- "Why? Show the numbers" shows people, vehicles, old and new green time for every road

**Traffic lights panel**
- shows the connected lights with green, yellow and red, and a countdown
- runs the normal fixed timer until the officer accepts or overrides
- yellow is always 3 seconds, Roadmind never touches it

**💬 Ask Roadmind**
A chat box that opens from the top bar. The officer can ask in Bangla, Banglish or English, like a normal chat:
- "রোড ২-এ মেলার ভিড় আসছে, দ্বিগুণ হবে, ১ ঘণ্টার প্ল্যান দাও"
- "office chutir por road 1 ar road 3 e bhir barbe, 45 minute"
- "Road 2 will get empty in half an hour"
- "এখন কোন রাস্তায় কত মানুষ?", "এই পরামর্শ কেন?", "বৃষ্টিতে কী করব?"

Any road, several roads together, any length of time from 5 minutes to 4 hours, and a crowd that grows or falls. For a plan, Roadmind answers in Bangla with:
- the green time for each road, before and after
- how many people would be stuck at the end with the normal timer, and with the plan
- a warning when the lights alone can't handle the crowd and extra police are needed

The plan also goes to the advice card. If the officer accepts, the lights run it for that time and then go back to the normal timer.

**🌧 Heavy rain**
In heavy rain a bus or rickshaw can be partly hidden behind a truck, so the camera counts too few people on that road. Roadmind checks every truck: if another vehicle's box is 20% or more covered by it, that vehicle counts as partly hidden. Roadmind knows it's raining when the officer presses 🌧 or when the picture is blurry. If it's raining and a vehicle may be hidden, Roadmind does not cut any road's green time. It keeps the current split and says why. Cutting a road's time because of a wrong count would make a whole bus wait longer, so we chose to play safe.

**Other things**
- **🚑 Emergency** gives an ambulance's road green first (only a simulation for now)
- **⬆ Upload video** to try any traffic video
- **📷 Camera** for a phone (IP Webcam app), a CCTV RTSP link, or the laptop webcam
- every decision is saved in a log with a snapshot

Upload video and Camera are only for the demo and for testing (see "Why the Upload and Camera buttons are there" below).

## How the plan is calculated

1. **Read the question.** With a Gemini key, Gemini reads the officer's message and fills a small form: which roads, how much the crowd changes, for how long. Without internet our own keyword rules fill the same form.
2. **Count.** The camera gives the people waiting on each road right now.
3. **Add the change.** A crowd grows step by step, so over the period a road that "doubles" has on average 1.5 times today's demand.
4. **Share the green.** Each road gets at least 10 seconds, and the rest of the 120-second cycle is shared by people, with a maximum of 60 seconds per road. A road that gets busier never loses green. A road that gets emptier never gains green.
5. **Check the result.** Minute by minute we work out how many people arrive and how many get through. That gives the people stuck at the end, with the normal timer and with the plan.
6. **Write the answer.** Gemini writes a natural Bangla reply from these numbers. If the reply has any number we didn't give it, we don't show it and use our own Bangla text instead.

The AI only reads the question and writes the sentence. Every number comes from the camera and these rules, so we can show where each one came from.

## About our demo video

For the demo we use a **recorded** traffic video (40 seconds, playing in a loop), not a live junction camera. So some features can't fully happen in the demo, even though the code for them is there:

| Feature | What you see in the demo | What happens at a real junction |
|---|---|---|
| Traffic lights | a lights panel in the app | Accept sends the timing to the real signal controller |
| Festival rush plan | the plan, its numbers and the lights panel changing | the crowd really grows, and the plan runs for the full time |
| Heavy rain | the 🌧 button and the "no green is cut" message (our clip is from a dry day) | real rain makes the picture blurry and Roadmind notices it by itself |
| Emergency | a simulated ambulance on the road you pick | an ambulance detected or reported on a real road |
| Waiting time | resets every 40 seconds when the clip loops | grows for as long as the vehicles really wait |
| Advice | the same traffic repeats, so the advice is often similar | traffic changes all day, so the advice changes with it |

So the advice in the demo is an example of how Roadmind decides, not a real decision for a real junction. The backend is the same one that would run at a real junction. Only the video source and the lights connection would change.

### Why the Upload and Camera buttons are there

We added **⬆ Upload video** and **📷 Camera** so we could show and test Roadmind without a real junction: judges can try any traffic video, and we can point a phone camera at a road.

At a real junction the officer wouldn't use them. Each junction's CCTV camera would be connected once, when Roadmind is set up there (its RTSP link goes in that junction's file in `junctions/`). After that Roadmind starts watching by itself, and the officer only sees the advice, the chat and the lights. So in a real version these two buttons would be removed from the officer's screen, or kept only for the person who sets the system up.

## How Roadmind makes each decision (backend)

Every few frames the backend does this:

1. **Read a frame** from the video, phone or CCTV (`app/video/source.py`).
2. **Find vehicles and people** with YOLO11n and follow each one with ByteTrack, so we know how long it has been waiting (`app/video/detector.py`, `app/video/tracker.py`).
3. **Count per road.** Each road is an area on the picture. We count the vehicles inside it and turn them into people with the averages above (`app/core/people.py`). For every truck we also count how many other vehicles are partly behind it.
4. **Check the camera.** If the picture is dark, blurry or blocked, confidence goes down (`app/video/confidence.py`).

Then, once per cycle (or when the officer asks), Roadmind decides (`app/core/advisor.py`, `app/pipeline.py`). It goes through these checks in order:

1. **No roads found yet:** no advice, keep looking.
2. **Low camera confidence (and no emergency):** don't guess. Advise keeping the normal timer.
3. **Emergency:** that road gets 30 seconds of green first, and the other roads share the rest.
4. **No vehicles at all:** keep the current timing.
5. **Heavy rain and a vehicle partly behind a truck:** the count may be too low, so keep the current split and cut no road's green.
6. **Normal case:** share the cycle by people waiting, 10 to 60 seconds per road. Roads where someone waited over 2 minutes go first, and if 8 or more people are waiting to cross, they get extra walking time.
7. **Only advise a change if it matters:** if no road would gain at least 3 seconds, say the current plan already fits.

After that:

- **Explain:** the numbers go into a Bangla and English sentence. Gemini can make the Bangla sound more natural, but if it changes any number we use our own sentence (`app/core/explain.py`).
- **Save:** the advice, the numbers and a snapshot go into the decision log (SQLite, `app/db.py`).
- **Officer decides:** Accept sends the advised green times to the lights. Override uses the officer's seconds, kept within 10 to 60, and saves the reason. Each advice can be decided only once. With no decision, the lights keep their current timing.
- **Ask Roadmind plans:** the same rules, but for future demand on the roads the officer names (see "How the plan is calculated"). An accepted plan runs for its time, then the lights go back to what they were running before.

## Rules we follow

- every road gets at least 10 and at most 60 seconds of green
- if vehicles on a road have waited more than 2 minutes, that road goes first
- if 8 or more people are waiting to cross, they get extra walking time
- if the camera is dark, blurry or blocked, Roadmind doesn't guess. It says to keep the normal timer
- if a bus is detected with low confidence, we count it as a truck, so we don't add 40 people by mistake
- no number plates are read and no faces are identified, and the video stays on the computer

## Tools we used

| What | Tool |
|---|---|
| Finding vehicles and people | YOLO11n (Ultralytics) |
| Following each vehicle, waiting time | ByteTrack (built into Ultralytics), supervision |
| Video and drawing | OpenCV |
| Backend | Python, FastAPI, Uvicorn |
| Live updates to the page | Server-Sent Events and an MJPEG video stream |
| Decision log | SQLite |
| Reading questions and writing Bangla replies | Google Gemini (optional, `google-genai`) |
| Bangla voice | edge-tts (Microsoft Bangla voice), with the browser's voice as backup |
| Dashboard | plain HTML, CSS and JavaScript, Noto Sans Bengali and Inter fonts |
| Hosting | Docker, Render |
| Tests | pytest |

We also used Claude to help write the code and documents. All licences are in [CREDITS.md](CREDITS.md).

## How to run it

You need Python 3.11 or newer. We used 3.14 on Windows.

First time:

```
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Every time:

```
.venv\Scripts\activate
python -m uvicorn app.main:app
```

Then open http://localhost:8000. The first run downloads the YOLO model. After that it works without internet, except Gemini and the Bangla voice. For Gemini, put your key in `.env` after `GEMINI_API_KEY=`. Never put the key on GitHub.

To try your own footage, press **Upload video**, or press **Camera** and type a phone's IP Webcam address, a CCTV RTSP link, or `0` for the laptop webcam. Use a camera that is high up and sees traffic from at least two directions.

Problems we ran into on Windows:

- `pip.exe` blocked by Application Control: use `python -m pip` instead
- error about Visual C++ Redistributable or `c10.dll`: install https://aka.ms/vs/17/release/vc_redist.x64.exe
- "running scripts is disabled": run `Set-ExecutionPolicy -Scope Process Bypass` first
- after updating, if some buttons look empty, press Ctrl + F5 in the browser

Run the tests with `python -m pytest`.

## Running it online

There is a Dockerfile, so it runs on Render or any Docker host. Our junction video (`data/clips/demo.mp4`) is in the repo, so the online version starts by itself with nothing to upload.

On Render, add these environment variables:

| Key | Value |
|---|---|
| `ROADMIND_SLOW_MODE` | `1` |
| `ROADMIND_IMG_SIZE` | `320` |
| `GEMINI_API_KEY` | your key (optional) |

### Why the online version is slower than on our laptop

- **The free server is small.** Render's free plan gives a tiny part of one CPU and no graphics card. On our laptop the AI checks 10 to 20 pictures a second. Online it checks about 1 picture a second.
- **The video still plays smoothly.** We play the video at normal speed and the AI works on the newest picture it can get. So the boxes around the vehicles move a little late and jump instead of sliding. The counts and the advice are still right, because traffic doesn't change much in one second.
- **A lighter stream.** Online we send about 12 pictures a second, a bit smaller and a bit more compressed, so it also loads on slow internet.
- **Finding the roads takes longer.** For a newly uploaded video, the video waits for the AI while the roads are being found, because the AI has to see the cars move. After that it plays at normal speed. Our own junction video already has its roads saved, so it starts smoothly.
- **The first visit is slow.** A free Render app goes to sleep when nobody uses it. The first visit can take up to a minute while it wakes up and loads the AI model.

For full speed, run it on a laptop.

## What's not done yet

- the model doesn't know CNG, rickshaw or leguna yet. We need to train it on Bangladeshi vehicles
- people per vehicle is an estimate, not a real count
- sometimes a lorry is detected as a bus
- how much a crowd will grow comes from the officer. Next we want the camera to re-check every few minutes and update the plan by itself
- road names come from the junction file. Later we want to use a map service so Roadmind knows which road is which
- we haven't tested it at a real junction yet, so we don't know how much waiting time it saves. The traffic light panel in the app stands in for a real signal controller
- we haven't measured accuracy on a big dataset yet. `scripts/evaluate_counts.py` can compare the AI's count with a hand count

## Credits

All libraries, models and fonts with their licences are in [CREDITS.md](CREDITS.md). We used Claude to help with code and documents, Gemini for the Bangla sentences and chat replies in the app, and YOLO for detection. Since YOLO is AGPL-3.0, this project is open source under the same licence.

## Team

- Ehsanul Alam
- K.A Shahriar Rubaiyat
- MD. Ikram Hossain Sami
