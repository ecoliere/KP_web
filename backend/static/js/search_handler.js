document.addEventListener('DOMContentLoaded', function() {
    const resultsList = document.getElementById('search-results-list');
    const errorDisplay = document.getElementById('search-error-display');

    function displaySearchError(message) {
        if (!errorDisplay) return; 
        errorDisplay.textContent = message;
        errorDisplay.style.display = message ? 'block' : 'none';
    }

    function updateActionButtons(buttonContainer, newStatus, userId) {
        if (!buttonContainer || !userId) return;

        let newButtonsHtml = ''; 

        switch (newStatus) {
            case 'pending_sent': 
                newButtonsHtml = `<button class="btn-cancel-request" data-action="cancel">Отменить заявку</button>`;
                break;
            case 'accepted': 
                newButtonsHtml = `<span class="friends-status">Друзья</span>`;
                break;
            case 'not_friends': 
                newButtonsHtml = `<button class="btn-add-friend" data-action="add">Добавить в друзья</button>`;
                break;
             case 'pending_received': 
                 newButtonsHtml = `<button class="btn-accept" data-action="accept">Принять</button> <button class="btn-decline" data-action="decline">Отклонить</button>`;
                 break;
            default: 
                 newButtonsHtml = `<span class="error-status">Ошибка статуса</span>`;
                 console.error("Unknown status received for button update:", newStatus);
                 break;
        }

        buttonContainer.innerHTML = newButtonsHtml;        
    }


    async function handleSearchFriendAction(action, userId, buttonElement) {
        const buttonContainer = buttonElement.closest('.search-result-actions');
        if (!action || !userId || !buttonContainer) {
            console.error("Action, userId or buttonContainer missing.", {action, userId, buttonContainer});
            displaySearchError("Внутренняя ошибка: не удалось обработать нажатие.");
            return;
        }

        buttonContainer.querySelectorAll('button').forEach(btn => btn.disabled = true);
        const originalHtml = buttonContainer.innerHTML;

        const apiUrl = `/api/friend/${action}/${userId}`;
        displaySearchError('');

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (response.ok && result.success) {
                console.log(`${action} action successful for user ${userId}`);

                let nextStatus = 'unknown';
                if (action === 'add') {
                    nextStatus = 'pending_sent'; 
                } else if (action === 'cancel') {
                    nextStatus = 'not_friends'; 
                } else if (action === 'accept') {
                    nextStatus = 'accepted'; 
                } else if (action === 'decline') {
                    nextStatus = 'not_friends'; 
                } else if (action === 'remove') { 
                    nextStatus = 'not_friends';
                }

                updateActionButtons(buttonContainer, nextStatus, userId);

            } else {
                console.error(`API Error (${action}) for user ${userId}:`, result.message || result.error || 'Unknown API error');
                displaySearchError(result.message || result.error || `Действие '${action}' не удалось.`);
                 buttonContainer.innerHTML = originalHtml;
                 buttonContainer.querySelectorAll('button').forEach(btn => btn.disabled = false);
            }

        } catch (error) {
            console.error(`Network or fetch error during ${action} for user ${userId}:`, error);
            displaySearchError(`Сетевая ошибка при действии '${action}'. Попробуйте позже.`);
             buttonContainer.innerHTML = originalHtml;
             buttonContainer.querySelectorAll('button').forEach(btn => btn.disabled = false);
        }
    }

    if (resultsList) {
        resultsList.addEventListener('click', (event) => {
            const target = event.target;

            const actionButton = target.closest('button[data-action]');

            if (!actionButton) {
                return;
            }

            const action = actionButton.dataset.action;

            const listItem = actionButton.closest('li[data-user-id]');
            const userId = listItem ? listItem.dataset.userId : null;

            if (action && userId) {
                handleSearchFriendAction(action, userId, actionButton);
            } else {
                console.error("Could not find action or user ID for the button click.", {action, userId});
                displaySearchError("Ошибка: Не удалось определить действие или пользователя.");
            }
        });
    } else {
        console.log("Search results list not found on the page.");
    }

}); 