// ==UserScript==
// @name         Flazu Bypass (working)
// @namespace    flazu.bypass.auto.v4
// @version      4.3
// @description  does his work
// @author       flazu team
// @match        *://auth.platoboost.app/
// @match        *://*.linkvertise.com/*
// @match        *://*.linkvertise.net/*
// @match        *://*.loot-link.com/*
// @match        *://*.lootdest.info/*
// @match        *://*.rekonise.com/*
// @match        *://*.platoboost.app/*
// @match        *://adf.ly/*
// @match        *://*.adf.ly/*
// @grant        GM_addStyle
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';  
    console.log("[Flazu AUTH+] Script loaded.");  

    function createGUI() {  
        const gui = document.createElement("div");  
        gui.id = "flazu-screen";  
        gui.innerHTML = `  
            <div class="panel">  
                <h1>Flazu Bypass</h1>  
                <p class="status">Bypassing...</p>  
                <div class="timer">00:00:000</div>  
                <div class="loader"></div>  
            </div>  
        `;  
        document.body.appendChild(gui);  
        applyStyles();  
        startBypass();  
    }  

    function applyStyles() {  
        GM_addStyle(`  
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
            #flazu-screen {  
                position: fixed;  
                top: 0; left: 0;  
                width: 100vw; height: 100vh;  
                background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%);  
                display: flex;  
                justify-content: center;  
                align-items: center;  
                font-family: 'Poppins', sans-serif;  
                z-index: 999999999999;  
                color: #ffffff;  
                overflow: hidden;
            }  
            .panel {  
                width: 500px;  
                padding: 60px;  
                border-radius: 35px;  
                background: rgba(255,255,255,0.1);  
                backdrop-filter: blur(20px);  
                box-shadow: 0 10px 40px rgba(0,0,0,0.9);  
                text-align: center;  
                animation: fadeIn 0.7s ease-out;  
                position: relative;
            }  
            @keyframes fadeIn {  
                from { opacity:0; transform: translateY(30px) scale(0.9); }  
                to { opacity:1; transform: translateY(0) scale(1); }  
            }  
            h1 { 
                font-size: 2.8rem; 
                margin-bottom: 15px; 
                text-shadow: 0 0 20px #00ffb3cc; 
                letter-spacing: 1px;
            }  
            .status { 
                opacity: 0.95; 
                margin-bottom: 20px; 
                font-size: 1.3rem;
                font-weight: 600;
                letter-spacing: 0.5px;
            }  
            .timer {  
                margin-top: 20px;  
                font-size: 1.6rem;  
                font-weight: bold;  
                text-shadow: 0 0 15px #00ffb3;  
            }  
            .loader {  
                width: 70px;  
                height: 70px;  
                border: 6px solid #ffffff25;  
                border-top: 6px solid #00ffb3;  
                border-radius: 50%;  
                margin: 35px auto;  
                animation: spin 0.9s linear infinite;  
            }  
            @keyframes spin {  
                to { transform: rotate(360deg); }  
            }  
            .result-box {  
                margin-top: 30px;  
                padding: 25px;  
                border-radius: 20px;  
                background: rgba(0,0,0,0.6);  
                font-size: 1.1rem;  
                word-break: break-all;  
                box-shadow: inset 0 0 15px rgba(0,255,179,0.3);
                transition: all 0.3s ease;
            }  
            .result-box:hover {
                box-shadow: inset 0 0 20px rgba(0,255,179,0.5);
            }
            .btn-action {  
                margin-top: 25px;  
                padding: 16px 35px;  
                border: none;  
                border-radius: 20px;  
                color: white;  
                font-size: 1.3rem;  
                font-weight: 600;
                cursor: pointer;  
                transition: 0.4s ease;  
            }  
            .btn-open { background: linear-gradient(135deg, #00c853, #009624); }  
            .btn-copy { background: linear-gradient(135deg, #2979ff, #004ecb); }  
            .btn-action:hover { 
                transform: translateY(-5px) scale(1.08); 
                box-shadow: 0 8px 20px rgba(0,255,179,0.5);
            }  
            .redirect-timer {  
                margin-top: 20px;  
                font-size: 1.2rem;  
                opacity: 0.95;  
            }  
            .redirect-timer span {
                color: #00ffb3;
                font-weight: bold;
            }
        `);  
    }  

    function startBypass() {  
        const currentURL = window.location.href;  
        console.log("[Flazu AUTH+] Target →", currentURL);  
        const isLinkvertise = currentURL.includes("linkvertise.com") || currentURL.includes("linkvertise.net");  

        const timerElement = document.querySelector(".timer");  
        let startTime = performance.now();  
        const interval = setInterval(() => {  
            let elapsed = performance.now() - startTime;  
            let min = Math.floor(elapsed / 60000).toString().padStart(2, '0');  
            let sec = Math.floor((elapsed / 1000) % 60).toString().padStart(2, '0');  
            let ms = Math.floor(elapsed % 1000).toString().padStart(3, '0');  
            timerElement.innerText = min + ':' + sec + ':' + ms;  
        }, 10);  

        let bypassRequest;  
        if (currentURL.includes("rekonise.com")) {  
            bypassRequest = fetch("https://api.rekonise.com/social-unlocks/a-train-moveset-rcfwc/unlock", {  
                method: "GET",  
                headers: {  
                    "accept": "application/json, text/plain, */*",  
                    "origin": "https://rekonise.com",  
                    "referer": "https://rekonise.com/",  
                    "sec-fetch-site": "same-site"  
                }  
            }).then(res => res.json()).then(json => json.url);  
        } else {  
            bypassRequest = fetch(`https://bypass.flazu.my/v1/free/bypass?link=${encodeURIComponent(currentURL)}`)
                .then(r => r.text())
                .then(text => {
                    try {
                        const json = JSON.parse(text);
                        if (json.status === "success" && json.key) {
                            return json.key;
                        } else {
                            return text;
                        }
                    } catch (e) {
                        return text;
                    }
                });
        }  

        bypassRequest.then(result => {  
            clearInterval(interval);  
            const panel = document.querySelector(".panel");  
            const statusElement = document.querySelector(".status");
            if (isLinkvertise) {
                statusElement.innerText = "Detected as Luarmor Linkvertise. Redirecting to the response in 25 seconds.";
                statusElement.style.fontSize = "1.4rem";
                statusElement.style.color = "#00ffb3";
            } else {
                statusElement.innerText = "Bypass complete";
            }  
            document.querySelector(".loader").style.display = "none"; // Hide loader after bypass  
            panel.innerHTML += `<div class="result-box">${result}</div>`;  

            const isURL = result.startsWith("http://") || result.startsWith("https://");  

            if (isURL) {  
                const btnText = isLinkvertise ? "Open now (at your own risk)" : "Open";  
                panel.innerHTML += `<button class="btn-action btn-open">${btnText}</button>`;  
                const openBtn = document.querySelector(".btn-open");  

                // Add redirect timer display  
                const redirectDelay = isLinkvertise ? 25000 : 5000;  
                let remaining = Math.ceil(redirectDelay / 1000);  
                panel.innerHTML += `<p class="redirect-timer">Auto-redirecting in <span class="countdown">${remaining}</span> seconds</p>`;  
                const countdownElement = document.querySelector(".countdown");  

                const countdownInterval = setInterval(() => {  
                    remaining--;  
                    countdownElement.innerText = remaining;  
                    if (remaining <= 0) {  
                        clearInterval(countdownInterval);  
                        window.location.href = result;  
                    }  
                }, 1000);  

                // If open button is clicked, it redirects immediately (skipping the timer)  
                openBtn.onclick = () => {  
                    clearInterval(countdownInterval);  
                    window.location.href = result;  
                };  
            } else {  
                panel.innerHTML += `<button class="btn-action btn-copy">Copy</button>`;  
                const copyBtn = document.querySelector(".btn-copy");
                copyBtn.onclick = async () => {  
                    try {
                        await navigator.clipboard.writeText(result);
                        copyBtn.innerText = "Copied!";
                        setTimeout(() => {
                            copyBtn.innerText = "Copy";
                        }, 2000);
                    } catch (err) {
                        console.error("Failed to copy: ", err);
                        copyBtn.innerText = "Copy Failed";
                    }
                };  
            }  
        })  
        .catch(err => {  
            clearInterval(interval);  
            console.error("[Flazu AUTH+] ERROR:", err);  
            document.querySelector(".status").innerText = "Error";  
        });  
    }  

    if (document.readyState === "complete" || document.readyState === "interactive") {  
        createGUI();  
    } else {  
        document.addEventListener("DOMContentLoaded", createGUI);  
    }  
})();
