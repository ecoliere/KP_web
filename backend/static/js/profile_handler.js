document.addEventListener('DOMContentLoaded', function() {
    const actionButtonContainer = document.getElementById('profile-action-buttons');
    const errorDisplay = document.getElementById('profile-actions-error');

    function displayProfileError(message) {
        if (!errorDisplay) return;
        errorDisplay.textContent = message;
        errorDisplay.style.display = message ? 'block' : 'none';
    }

    function updateProfileButtons(newStatus, userId) {
        if (!actionButtonContainer || !userId) return;

        let newButtonsHtml = '';
        switch (newStatus) {
            case 'pending_sent': 
                newButtonsHtml = `
                    <button class="btn-profile-action btn-cancel" data-action="cancel">
                        <i class="bi bi-x-circle-fill"></i> Отменить заявку
                    </button>`;
                break;
            case 'accepted': 
                newButtonsHtml = `
                    <button class="btn-profile-action btn-remove" data-action="remove">
                        <i class="bi bi-person-dash-fill"></i> Удалить из друзей
                    </button>
                    `;
                break;
            case 'not_friends': 
                newButtonsHtml = `
                    <button class="btn-profile-action btn-add" data-action="add">
                        <i class="bi bi-person-plus-fill"></i> Добавить в друзья
                    </button>`;
                break;
            case 'pending_received': 
                 newButtonsHtml = `
                     <button class="btn-profile-action btn-accept" data-action="accept">
                         <i class="bi bi-check-lg"></i> Принять заявку
                     </button>
                     <button class="btn-profile-action btn-decline" data-action="decline">
                         <i class="bi bi-x-lg"></i> Отклонить
                     </button>`;
                 break;
            default:
                newButtonsHtml = `<span class="error-status">Ошибка статуса</span>`;
                console.error("Unknown status received for profile button update:", newStatus);
                break;
        }

        actionButtonContainer.innerHTML = newButtonsHtml;
    }

    async function handleProfileAction(action, userId, buttonElement) {
        if (!action || !userId || !actionButtonContainer) return;

        actionButtonContainer.querySelectorAll('button').forEach(btn => btn.disabled = true);
        const originalHtml = actionButtonContainer.innerHTML; 
        displayProfileError(''); 

        const apiUrl = `/api/friend/${action}/${userId}`;

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            const result = await response.json();

            if (response.ok && result.success) {
                console.log(`Profile action ${action} successful for user ${userId}`);
                let nextStatus = 'unknown';
                if (action === 'add') nextStatus = 'pending_sent';
                else if (action === 'cancel') nextStatus = 'not_friends';
                else if (action === 'accept') nextStatus = 'accepted';
                else if (action === 'decline') nextStatus = 'not_friends';
                else if (action === 'remove') nextStatus = 'not_friends';

                updateProfileButtons(nextStatus, userId); 

            } else {
                console.error(`API Error (${action}) for user ${userId}:`, result.message || result.error || 'Unknown API error');
                displayProfileError(result.message || result.error || `Действие '${action}' не удалось.`);
                actionButtonContainer.innerHTML = originalHtml;
                actionButtonContainer.querySelectorAll('button').forEach(btn => btn.disabled = false);
            }
        } catch (error) {
            console.error(`Network or fetch error during ${action} for user ${userId}:`, error);
            displayProfileError(`Сетевая ошибка при действии '${action}'. Попробуйте позже.`);
            actionButtonContainer.innerHTML = originalHtml;
            actionButtonContainer.querySelectorAll('button').forEach(btn => btn.disabled = false);
        }
    }

    if (actionButtonContainer) {
        const profileUserId = actionButtonContainer.dataset.profileUserId; 

        if (!profileUserId) {
            console.error("Profile user ID not found in data attribute!");
            return; 
        }

        actionButtonContainer.addEventListener('click', (event) => {
            const target = event.target;
            const actionButton = target.closest('button[data-action]');

            if (actionButton) {
                const action = actionButton.dataset.action;
                handleProfileAction(action, profileUserId, actionButton);
            }
        });
    }

});