const currentDomain = new URL(window.location.href).hostname;

chrome.storage.local.get([currentDomain], (data) => {
    if (data[currentDomain] && data[currentDomain].safe === false) {
        const warningBanner = document.createElement('div');
        warningBanner.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                background-color: red;
                color: white;
                text-align: center;
                padding: 10px;
                font-size: 16px;
                z-index: 9999;">
                ⚠️ Warning: This site may not be safe! 
                <br> Consider alternatives:
                ${data[currentDomain].alternatives.map(alt => `<a href="${alt.url}" style="color: white; margin: 0 5px;">${alt.name}</a>`).join('')}
            </div>
        `;

        document.body.prepend(warningBanner);
    }
});
