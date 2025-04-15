from flask import Flask, request, send_file
from gtts import gTTS
from pydub import AudioSegment
from pydub.effects import high_pass_filter, low_pass_filter
import os
import speech_recognition as sr
import tempfile
import time

app = Flask(__name__)

def apply_reverb(audio, reverb_amount):
    if reverb_amount <= 0:
        return audio
    delay_ms = 50
    decay = 0.5 * (reverb_amount / 100)
    delayed = audio._spawn(audio.raw_data, overrides={"frame_rate": audio.frame_rate})
    delayed = delayed[:len(audio) - int(delay_ms * audio.frame_rate / 1000)]
    delayed = delayed.fade_in(10).fade_out(10)
    delayed = delayed - (20 - reverb_amount / 5)
    return audio.overlay(delayed)

def smooth_audio(audio):
    return low_pass_filter(audio, 4000)

def clean_noise(audio):
    audio = high_pass_filter(audio, 100)
    audio = low_pass_filter(audio, 8000)
    return audio

def change_pitch(audio, semitones):
    if semitones == 0:
        return audio
    factor = 2.0 ** (semitones / 12.0)
    new_audio = audio._spawn(audio.raw_data, overrides={
        "frame_rate": int(audio.frame_rate * factor)
    })
    return new_audio.speedup(1.0 / factor)

def analyze_audio(audio_file):
    print(f"Analyzing audio: {audio_file}")  # Debug
    try:
        audio = AudioSegment.from_file(audio_file)
        avg_amplitude = audio.dBFS
        print(f"Audio analyzed - Amplitude: {avg_amplitude}")  # Debug
        return {"pitch_shift": 0, "volume_adjust": avg_amplitude}
    except Exception as e:
        print(f"Error analyzing audio: {str(e)}")  # Debug
        raise
    finally:
        print(f"Finished analyzing: {audio_file}")  # Debug

def apply_cloning(audio, clone_params):
    print(f"Applying cloning with params: {clone_params}")  # Debug
    audio = change_pitch(audio, clone_params.get("pitch_shift", 2))
    audio = audio + clone_params.get("volume_adjust", 1)
    return audio

def safe_remove(file_path):
    print(f"Attempting to remove: {file_path}")  # Debug
    retries = 3
    for i in range(retries):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Removed: {file_path}")  # Debug
            return
        except PermissionError as e:
            print(f"Retry {i+1}/{retries} - File locked: {e}")  # Debug
            time.sleep(0.5)  # Wait before retry
    print(f"Could not remove {file_path}, skipping.")  # Debug

@app.route('/')
def index():
    print("Serving index.html")  # Debug
    try:
        with open('index.html', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading index.html: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/convert', methods=['POST'])
def convert():
    print("Received convert request")  # Debug
    text = request.form['text']
    lang = request.form['lang']
    emotion = request.form.get('emotion', 'normal')
    pitch = float(request.form.get('pitch', 0))
    tempo = float(request.form.get('tempo', 1))
    reverb = float(request.form.get('reverb', 0))
    smooth = request.form.get('smooth') == 'on'
    noise_clean = request.form.get('noise_clean') == 'on'
    clone_audio = request.files.get('clone_audio')

    try:
        # Emotion ke hisaab se text tweaks
        if emotion == "funny":
            text = text + " హాహా!"
        elif emotion == "comedy":
            text = "హే, హే! " + text
        elif emotion == "angry":
            text = text + " గర్ర్!"

        # gTTS se audio generate kar
        print(f"Generating audio with text: {text}, lang: {lang}")  # Debug
        tts = gTTS(text=text, lang=lang)
        temp_file = "temp.mp3"
        tts.save(temp_file)

        # Audio ko load kar pydub se
        try:
            audio = AudioSegment.from_mp3(temp_file)
            print(f"Loaded audio: {temp_file}")  # Debug
        except Exception as e:
            print(f"FFmpeg error: {str(e)}")
            raise Exception("FFmpeg not installed or configured.")

        # Emotion ke hisaab se tweaks
        if emotion == "funny":
            audio = audio + 3
            audio = audio.speedup(playback_speed=1.3)
        elif emotion == "comedy":
            audio = audio + 5
            audio = audio.speedup(playback_speed=1.2)
        elif emotion == "angry":
            audio = audio - 3
            audio = audio.speedup(playback_speed=1.1)
        elif emotion == "narration":
            audio = audio - 2
            audio = audio.speedup(playback_speed=0.9)

        # Pitch control
        audio = change_pitch(audio, pitch)

        # Tempo control
        if tempo != 1:
            audio = audio.speedup(playback_speed=tempo)

        # Voice smoothing
        if smooth:
            audio = smooth_audio(audio)

        # Noise cleaning
        if noise_clean:
            audio = clean_noise(audio)

        # Reverb
        audio = apply_reverb(audio, reverb)

        # Voice cloning
        if clone_audio:
            print("Processing clone audio")  # Debug
            clone_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            clone_temp_name = clone_temp.name
            try:
                clone_audio.save(clone_temp_name)
                print(f"Saved clone audio: {clone_temp_name}")  # Debug
                clone_params = analyze_audio(clone_temp_name)
                audio = apply_cloning(audio, clone_params)
            except Exception as e:
                print(f"Cloning error: {str(e)}")  # Debug
                raise
            finally:
                clone_temp.close()  # Explicitly close the file
                safe_remove(clone_temp_name)  # Safe deletion

        # Final audio save kar
        output_file = "output.mp3"
        audio.export(output_file, format="mp3")
        print(f"Exported audio: {output_file}")  # Debug

        # Temporary file delete kar
        safe_remove(temp_file)

        print(f"Sending audio file: {output_file}")  # Debug
        return send_file(output_file, mimetype="audio/mp3")
    except Exception as e:
        print(f"Error: {str(e)}")  # Debug
        return f"Error: {str(e)}", 500

@app.route('/translate_audio', methods=['POST'])
def translate_audio():
    print("Received audio translation request")  # Debug
    audio_input = request.files['audio_input']
    target_lang = request.form['target_lang']
    target_emotion = request.form.get('target_emotion', 'normal')

    try:
        # Save uploaded audio temporarily
        audio_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        audio_temp_name = audio_temp.name
        try:
            audio_input.save(audio_temp_name)
            print(f"Saved translation audio: {audio_temp_name}")  # Debug
            # Speech to Text
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_temp_name) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)
            print(f"Recognized text: {text}")  # Debug
        except Exception as e:
            print(f"Speech recognition error: {str(e)}")  # Debug
            raise
        finally:
            audio_temp.close()
            safe_remove(audio_temp_name)

        # Emotion ke hisaab se text tweaks
        if target_emotion == "funny":
            text = text + " హాహా!"
        elif target_emotion == "comedy":
            text = "హే, హే! " + text
        elif target_emotion == "angry":
            text = text + " గర్ర్!"

        # gTTS se audio generate kar
        print(f"Generating translated audio with text: {text}, lang: {target_lang}")  # Debug
        tts = gTTS(text=text, lang=target_lang)
        temp_file = "temp_translated.mp3"
        tts.save(temp_file)

        # Audio ko load kar pydub se
        audio = AudioSegment.from_mp3(temp_file)

        # Emotion ke hisaab se tweaks
        if target_emotion == "funny":
            audio = audio + 3
            audio = audio.speedup(playback_speed=1.3)
        elif target_emotion == "comedy":
            audio = audio + 5
            audio = audio.speedup(playback_speed=1.2)
        elif target_emotion == "angry":
            audio = audio - 3
            audio = audio.speedup(playback_speed=1.1)
        elif target_emotion == "narration":
            audio = audio - 2
            audio = audio.speedup(playback_speed=0.9)

        # Final audio save kar
        output_file = "translated_output.mp3"
        audio.export(output_file, format="mp3")
        print(f"Exported translated audio: {output_file}")  # Debug

        # Temporary file delete kar
        safe_remove(temp_file)

        print(f"Sending translated audio file: {output_file}")  # Debug
        return send_file(output_file, mimetype="audio/mp3")
    except Exception as e:
        print(f"Translation error: {str(e)}")  # Debug
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    print("Starting Flask server...")  # Debug
    app.run(debug=True)