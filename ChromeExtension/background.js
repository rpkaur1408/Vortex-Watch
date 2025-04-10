chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'UPDATE_ICON') {
    chrome.action.setIcon({
      path: "icons/lock-open-solid.png"
    });
    
    chrome.action.setBadgeText({
      text: message.isSafe ? "✓" : "!"
    });
    
    chrome.action.setBadgeBackgroundColor({
      color: message.isSafe ? "#2ecc71" : "#e74c3c"
    });
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url && tab.url.startsWith("http")) {
    try {
      let domain = new URL(tab.url).hostname;
      chrome.storage.local.get([domain], (data) => {
        chrome.action.setIcon({
          tabId: tabId,
          path: "icons/lock-open-solid.png"
        });
        
        if (data[domain]) {
          chrome.action.setBadgeText({
            tabId: tabId,
            text: data[domain].safe ? "✓" : "!"
          });
          
          chrome.action.setBadgeBackgroundColor({
            tabId: tabId,
            color: data[domain].safe ? "#2ecc71" : "#e74c3c"
          });
          
          if (data[domain].safe === false) {
            chrome.action.openPopup();
          }
        } else {
          chrome.action.setBadgeText({
            tabId: tabId,
            text: ""
          });
        }
      });
    } catch (error) {
      console.error("Failed to parse URL:", tab.url, error);
    }
  }
});
