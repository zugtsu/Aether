import json
import sys
import time
import wave

import numpy as np
import sherpa_onnx


WINDOW, HOP, MAX_WINDOWS = 2.0, 1.0, 30


def clean(tag):
    return str(tag or "").strip().strip("<|>").strip()


def laugh_slices(rec, rate, audio):
    size, hop = int(WINDOW * rate), int(HOP * rate)
    if len(audio) < size * 1.25:
        return 0
    streams = []
    for start in range(0, len(audio) - size // 2, hop)[:MAX_WINDOWS]:
        s = rec.create_stream()
        s.accept_waveform(rate, audio[start:start + size])
        streams.append(s)
    rec.decode_streams(streams)
    return sum(clean(getattr(s.result, "event", "")) == "Laughter" for s in streams)


def speech_secs(audio, rate):
    f = int(0.03 * rate)
    if len(audio) < f:
        return 0.0
    e = np.sqrt((audio[: len(audio) // f * f].reshape(-1, f) ** 2).mean(axis=1))
    return round(float((e > 4 * np.percentile(e, 10)).sum()) * 0.03, 2)


def voiceprint(spk, rate, audio):
    s = spk.create_stream()
    s.accept_waveform(rate, audio)
    s.input_finished()
    v = np.array(spk.compute(s))
    return [round(float(x), 5) for x in v / (np.linalg.norm(v) or 1.0)]


def main():
    model = sys.argv[1]
    tokens = sys.argv[2]
    rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(model=model, tokens=tokens, num_threads=4, use_itn=True)
    spk = None
    if len(sys.argv) > 3 and sys.argv[3]:
        spk = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=sys.argv[3], num_threads=2))
    print(json.dumps({"ready": True, "speaker": spk is not None}), flush=True)
    for line in sys.stdin:
        try:
            req = json.loads(line)
            t0 = time.time()
            with wave.open(req.get("wav") or req["embed"], "rb") as w:
                rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
                raw = w.readframes(w.getnframes())
            if width != 2:
                raise ValueError("need 16-bit audio")
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if ch > 1:
                audio = audio.reshape(-1, ch).mean(axis=1)
            mine = {"voice": voiceprint(spk, rate, audio), "speech": speech_secs(audio, rate)} if spk else {}
            if "embed" in req:
                if not spk:
                    raise ValueError("no speaker model")
                print(json.dumps(mine), flush=True)
                continue
            s = rec.create_stream()
            s.accept_waveform(rate, audio)
            rec.decode_streams([s])
            r = s.result
            event = clean(getattr(r, "event", ""))
            out = {"text": r.text.strip(), "emotion": clean(getattr(r, "emotion", "")),
                   "event": event, "lang": clean(getattr(r, "lang", "")),
                   "laughs": 1 if event == "Laughter" else laugh_slices(rec, rate, audio),
                   **mine, "secs": round(time.time() - t0, 2)}
        except Exception as e:
            out = {"error": str(e)}
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
