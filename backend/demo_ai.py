import json
from audio_analyzer import analyze_audio

def run_demo():
    print("\n🤖 Booting up AI Video Editor Engine...")
    audio_file = "audio.wav"
    
    print(f"\n🎧 Listening to and analyzing: {audio_file}")
    results = analyze_audio(audio_file)
    
    print("\n✅ AI Analysis Complete!")
    print("\n🎵 Detected Beats (These timestamps are where the AI will automatically cut the video to the music):")
    if results['beats']:
        print(results['beats'][:15], "... (truncated)")
    else:
        print("No beats detected.")
    
    print("\n🤫 Detected Silences (These timestamps are where the AI will automatically apply Jump Cuts to remove dead air):")
    if results['silences']:
        for gap in results['silences'][:5]:
            print(f" - Jump Cut between {gap[0]}s and {gap[1]}s")
        if len(results['silences']) > 5:
            print("   ... and more")
    else:
        print("No silences detected.")
        
    print("\n📈 Waveform UI Data:")
    print(f"Generated {len(results['waveform'])} downsampled points for rendering the UI timeline.")

if __name__ == "__main__":
    run_demo()
