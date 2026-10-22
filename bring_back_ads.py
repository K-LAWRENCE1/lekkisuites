import io

print("Bringing back the ad video...")

p = "templates/index.html"
s = io.open(p, encoding="utf-8").read()

video_block = """            <video class="hero-video" autoplay loop muted playsinline>
                <source src="{{ url_for('static', filename='hotel.mp4') }}" type="video/mp4">
            </video>
            <div class="hero-overlay"></div>
            <button id="sound-toggle" class="sound-btn" type="button">&#128263;</button>
"""

marker = '<section class="hero" id="home">'

if 'hero-video' not in s:
    s = s.replace(marker, marker + "\n" + video_block, 1)
    print("Video block restored in index.html")
else:
    print("Video block already present - skipping")

old_scripts = '{% block scripts %}{% endblock %}'
new_scripts = """{% block scripts %}
    <script>
        const heroVideo = document.querySelector('.hero-video');
        const soundBtn = document.getElementById('sound-toggle');
        soundBtn.addEventListener('click', function () {
            heroVideo.muted = !heroVideo.muted;
            soundBtn.innerHTML = heroVideo.muted ? '&#128263;' : '&#128266;';
        });
    </script>
{% endblock %}"""

if old_scripts in s:
    s = s.replace(old_scripts, new_scripts, 1)
    print("Sound button script restored")
else:
    print("Script block not found in expected state - skipping (probably already restored)")

io.open(p, "w", encoding="utf-8", newline="").write(s)

p2 = "static/style.css"
css = io.open(p2, encoding="utf-8").read()

if 'hero-video' not in css:
    css = css + """

/* ===== AD VIDEO (restored) ===== */
.hero-video {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    z-index: 0;
}
.hero-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(to bottom, rgba(15, 28, 46, 0.2), rgba(15, 28, 46, 0.45));
    z-index: 1;
}
.hero .hero-content {
    position: relative;
    z-index: 3;
}
.sound-btn {
    position: absolute;
    bottom: 22px;
    right: 22px;
    z-index: 4;
    background: rgba(255, 255, 255, 0.2);
    border: none;
    color: #fff;
    width: 48px;
    height: 48px;
    font-size: 20px;
    cursor: pointer;
    backdrop-filter: blur(4px);
    transition: background 0.2s;
}
.sound-btn:hover {
    background: rgba(255, 255, 255, 0.35);
}
"""
    io.open(p2, "w", encoding="utf-8", newline="").write(css)
    print("Ad video styles restored in style.css")
else:
    print("Styles already present - skipping")

print("")
print("DONE - the ad video is back on the homepage.")
print("Now: press Ctrl+C on the server terminal, then run:  python app.py")
print("Then refresh the browser with Ctrl+F5.")
