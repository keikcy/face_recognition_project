let video = document.getElementById("video");
let canvas = document.getElementById("canvas");
let ctx = canvas.getContext("2d");

function startCamera() {
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            video.srcObject = stream;
            document.getElementById("status").innerText = "Camera started";
        })
        .catch(err => {
            document.getElementById("status").innerText = err;
        });
}

function captureFace() {
    const name = document.getElementById("name").value;
    const section_id = document.getElementById("section").value;

    if (!name) {
        alert("Enter name");
        return;
    }
    if (!section_id) {
        alert("Select section");
        return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    let imageData = canvas.toDataURL("image/jpeg");

    fetch("/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, section_id, image: imageData })
    })
    .then(r => r.json())
    .then(d => {
        document.getElementById("status").innerText = d.status || d.error;
    });
}

