import math
import random
import struct
import wave

SAMPLE_RATE = 44100
DURATION = 35.0  # seconds
BPM = 85.0
BEAT_DUR = 60.0 / BPM
BAR_DUR = BEAT_DUR * 4

# Scale / Frequencies (Hz) for C major 7th chord progression: Cmaj7 -> Am7 -> Dm7 -> G7
# Cmaj7: C4 (261.63), E4 (329.63), G4 (392.00), B4 (493.88)
# Am7:   A3 (220.00), C4 (261.63), E4 (329.63), G4 (392.00)
# Dm7:   D4 (293.66), F4 (349.23), A4 (440.00), C5 (523.25)
# G7:    G3 (196.00), B3 (246.94), D4 (293.66), F4 (349.23)

CHORDS = [
    [261.63, 329.63, 392.00, 493.88],  # Cmaj7
    [220.00, 261.63, 329.63, 392.00],  # Am7
    [293.66, 349.23, 440.00, 523.25],  # Dm7
    [196.00, 246.94, 293.66, 349.23],  # G7
]

# Bass notes for each chord
BASS_NOTES = [130.81, 110.00, 146.83, 98.00]  # C3, A2, D3, G2

total_samples = int(SAMPLE_RATE * DURATION)
samples_l = [0.0] * total_samples
samples_r = [0.0] * total_samples

random.seed(42)

def generate_lofi_track(filename="upbeat_lofi.wav"):
    num_bars = int(math.ceil(DURATION / BAR_DUR))

    # 1. Generate Lo-Fi Chords & Bass
    for bar in range(num_bars):
        bar_start_time = bar * BAR_DUR
        chord = CHORDS[bar % len(CHORDS)]
        bass = BASS_NOTES[bar % len(CHORDS)]

        # Play chord strum at start of bar and subtle swell at beat 2.5
        strum_times = [bar_start_time, bar_start_time + 2.5 * BEAT_DUR]

        for st in strum_times:
            if st >= DURATION:
                continue
            dur = BEAT_DUR * 2.2
            start_idx = int(st * SAMPLE_RATE)
            end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))

            for note_idx, freq in enumerate(chord):
                offset = int(note_idx * 0.025 * SAMPLE_RATE)  # Soft strum delay
                n_start = start_idx + offset
                n_end = min(total_samples, n_start + int(dur * SAMPLE_RATE))

                for i in range(n_start, n_end):
                    t = (i - n_start) / SAMPLE_RATE
                    # Soft triangular wave with warm harmonics for lo-fi e-piano sound
                    val = (
                        0.6 * math.sin(2 * math.pi * freq * t) +
                        0.25 * math.sin(2 * math.pi * (freq * 2.005) * t) +
                        0.15 * math.sin(2 * math.pi * (freq * 3.01) * t)
                    )
                    # Smooth envelope (attack + exponential decay)
                    env = math.sin(math.pi * min(1.0, t / 0.04)) * math.exp(-2.2 * t)
                    audio_val = val * env * 0.12

                    # Pan chord notes across stereo spectrum
                    pan = 0.3 + 0.4 * (note_idx / float(len(chord) - 1))
                    samples_l[i] += audio_val * (1.0 - pan)
                    samples_r[i] += audio_val * pan

        # Bass synth
        b_start = int(bar_start_time * SAMPLE_RATE)
        b_end = min(total_samples, b_start + int(BAR_DUR * 0.95 * SAMPLE_RATE))
        for i in range(b_start, b_end):
            t = (i - b_start) / SAMPLE_RATE
            # Warm sub-bass (sine + sub oct)
            val = 0.7 * math.sin(2 * math.pi * bass * t) + 0.3 * math.sin(2 * math.pi * (bass / 2.0) * t)
            env = math.sin(math.pi * min(1.0, t / 0.05)) * math.exp(-0.8 * t)
            b_val = val * env * 0.18
            samples_l[i] += b_val * 0.5
            samples_r[i] += b_val * 0.5

    # 2. Add Upbeat Lo-Fi Drum Beat (Kick, Snare, Hi-Hat)
    for bar in range(num_bars):
        bar_start_time = bar * BAR_DUR

        # Kick on beat 1, beat 2.5, beat 3.5
        kick_beats = [0.0, 1.75, 2.5]
        for kb in kick_beats:
            kt = bar_start_time + kb * BEAT_DUR
            if kt >= DURATION:
                continue
            k_start = int(kt * SAMPLE_RATE)
            k_len = int(0.18 * SAMPLE_RATE)
            k_end = min(total_samples, k_start + k_len)
            for i in range(k_start, k_end):
                t = (i - k_start) / SAMPLE_RATE
                # Pitch drop for punchy warm lo-fi kick
                freq = 110.0 * math.exp(-25.0 * t) + 45.0
                val = math.sin(2 * math.pi * freq * t) * math.exp(-12.0 * t) * 0.35
                samples_l[i] += val
                samples_r[i] += val

        # Soft Snare / Rimshot on beat 2 and 4
        snare_beats = [1.0, 3.0]
        for sb in snare_beats:
            st = bar_start_time + sb * BEAT_DUR
            if st >= DURATION:
                continue
            s_start = int(st * SAMPLE_RATE)
            s_len = int(0.15 * SAMPLE_RATE)
            s_end = min(total_samples, s_start + s_len)
            for i in range(s_start, s_end):
                t = (i - s_start) / SAMPLE_RATE
                noise = (random.random() * 2.0 - 1.0)
                body = math.sin(2 * math.pi * 180.0 * t) * math.exp(-30.0 * t)
                val = (0.6 * noise + 0.4 * body) * math.exp(-18.0 * t) * 0.22
                samples_l[i] += val * 0.55
                samples_r[i] += val * 0.45

        # Hi-Hats (8th notes with lo-fi swing)
        for hh in range(8):
            swing = 0.03 if (hh % 2 == 1) else 0.0
            ht = bar_start_time + (hh * 0.5 + swing) * BEAT_DUR
            if ht >= DURATION:
                continue
            h_start = int(ht * SAMPLE_RATE)
            h_len = int(0.05 * SAMPLE_RATE)
            h_end = min(total_samples, h_start + h_len)
            vol = 0.12 if (hh % 2 == 0) else 0.08
            for i in range(h_start, h_end):
                t = (i - h_start) / SAMPLE_RATE
                noise = (random.random() * 2.0 - 1.0)
                val = noise * math.exp(-80.0 * t) * vol
                samples_l[i] += val * 0.4
                samples_r[i] += val * 0.6

    # 3. Add Gentle Vinyl Crackle & Soft Master Filter
    for i in range(total_samples):
        # Subtle vinyl crackle pops
        if random.random() < 0.0008:
            pop = (random.random() * 2.0 - 1.0) * 0.04
            samples_l[i] += pop
            samples_r[i] += pop

    # 4. Normalize & Write to WAV
    max_val = max(max(abs(x) for x in samples_l), max(abs(x) for x in samples_r), 0.001)
    target_peak = 0.85
    norm_factor = target_peak / max_val

    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)

        out_bytes = bytearray()
        for i in range(total_samples):
            sl = int(max(-32768, min(32767, samples_l[i] * norm_factor * 32767)))
            sr = int(max(-32768, min(32767, samples_r[i] * norm_factor * 32767)))
            out_bytes.extend(struct.pack("<hh", sl, sr))

        wav_file.writeframes(out_bytes)

    print(f"Generated upbeat lo-fi track: {filename} ({DURATION}s)")

if __name__ == "__main__":
    generate_lofi_track()
