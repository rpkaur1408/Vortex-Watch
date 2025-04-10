document.addEventListener('DOMContentLoaded', function() {
    // Hide result div initially
    document.getElementById('result').style.display = 'none';
    
    chrome.tabs.query({ active: true, lastFocusedWindow: true }, async (tabs) => {
        if (!tabs.length) return;

        const currentURL = new URL(tabs[0].url);
        const currentDomain = currentURL.hostname;

        const loadingEl = document.getElementById('loading');
        const resultEl = document.getElementById('result');
        const alternativesEl = document.getElementById('alternatives');
        const alternativesList = document.querySelector('.alternatives-list');

        // Check if we have cached data for this domain
        chrome.storage.local.get([currentDomain], async (cachedData) => {
            if (cachedData[currentDomain] && cachedData[currentDomain].fullData) {
                const data = cachedData[currentDomain].fullData;
                loadingEl.style.display = 'none';
                resultEl.style.display = 'block';
                displayData(data, resultEl, alternativesEl, alternativesList, currentDomain);
                return;
            }
            
            try {
                const response = await fetch('http://localhost:5000/analyze', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ domain: currentDomain })
                });

                const data = await response.json();
                
                loadingEl.style.display = 'none';
                resultEl.style.display = 'block';

                if (data.status === 'success') {
                    chrome.storage.local.set({
                        [currentDomain]: {
                            safe: data.is_safe,
                            trustScore: data.trust_score || 0,
                            alternatives: data.alternatives || [],
                            fullData: data
                        }
                    });
                    
                    displayData(data, resultEl, alternativesEl, alternativesList, currentDomain);
                } else {
                    resultEl.innerHTML = `
                        <div class="warning">
                            <h2><i class="fas fa-exclamation-circle" style="color: #FFA500"></i> Warning</h2>
                            <p>${data.message || 'Unable to analyze this website. Use at your own risk.'}</p>
                        </div>
                    `;
                    alternativesEl.style.display = 'none';
                }
            } catch (error) {
                loadingEl.style.display = 'none';
                resultEl.innerHTML = `
                    <div class="error">
                        <h2><i class="fas fa-times-circle" style="color: #FF0000"></i> Error</h2>
                        <p>${error.message}</p>
                    </div>
                `;
                alternativesEl.style.display = 'none';
            }
        });
    });
});

function displayData(data, resultEl, alternativesEl, alternativesList, currentDomain) {
    const trustScore = data.trust_score || 0;
    const scoreColor = getTrustScoreColor(trustScore);
    
    // Hard-coded pill text and color
    const pillText = data.is_safe ? "Safe" : "Unsafe";
    const pillClass = data.is_safe ? "safe" : "unsafe";
    const pillColor = data.is_safe ? "#2ecc71" : "#e74c3c"; // Green for safe, red for unsafe

    resultEl.innerHTML = `
        <div class="trust-score-container">
            <h3>Trust Score: ${trustScore}/10</h3>
            <div class="progress-bar-container">
                <div class="progress-bar" style="width: ${trustScore * 10}%; background-color: ${scoreColor};"></div>
            </div>
            <div class="security-pill ${pillClass}" style="background-color: ${pillColor}; color: white;">${pillText}</div>
        </div>
        <div class="${data.is_safe ? 'safe' : 'unsafe'}">
            <h2><i class="fas ${data.is_safe ? 'fa-check-circle' : 'fa-exclamation-triangle'}" style="color: ${scoreColor}"></i> 
                ${data.is_safe ? 'Website is Safe' : 'Privacy Concerns Detected'}
            </h2>
            <p>${data.is_safe ? 'Privacy policy analysis indicates this site is safe to use.' : 
                (Array.isArray(data.policy_analysis[0]) ? data.policy_analysis[0][0] : data.policy_analysis[0])}</p>
            ${data.is_safe ? 
                `<p><a href="${data.privacy_policy}" target="_blank">View Privacy Policy <i class="fas fa-external-link-alt"></i></a></p>` :
                `<details>
                    <summary>See Details</summary>
                    <p>${Array.isArray(data.policy_analysis[0]) ? (data.policy_analysis[0][1] || 'No additional details available.') : 'No additional details available.'}</p>
                </details>`
            }
        </div>
    `;

    if (data.alternatives && data.alternatives.length > 0) {
        alternativesList.innerHTML = '';
        data.alternatives.forEach(alt => {
            const altDiv = document.createElement('div');
            altDiv.className = 'alternative-item';
            altDiv.innerHTML = `
                <h4>${alt.domain}</h4>
                <p>${alt.explanation}</p>
                <div class="alternative-links">
                    ${alt.data.privacy_policy ? `<a href="${alt.data.privacy_policy}" target="_blank">Privacy Policy</a>` : ''}
                    ${alt.data.terms_and_conditions ? `<a href="${alt.data.terms_and_conditions}" target="_blank">Terms & Conditions</a>` : ''}
                </div>
            `;
            alternativesList.appendChild(altDiv);
        });
        alternativesEl.style.display = 'block';
    } else {
        alternativesEl.style.display = 'none';
    }

    chrome.runtime.sendMessage({
        type: 'UPDATE_ICON',
        isSafe: data.is_safe,
        trustScore: trustScore
    });
}

function getTrustScoreColor(score) {
    if (score >= 8) {
        return '#2ecc71';
    } else if (score >= 6) {
        return '#27ae60';
    } else if (score >= 4) {
        return '#f39c12';
    } else if (score >= 2) {
        return '#e67e22';
    } else {
        return '#e74c3c';
    }
}
