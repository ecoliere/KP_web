document.addEventListener('DOMContentLoaded', () => {
    const requestList = document.getElementById('friend-requests-list');
    const errorDisplay = document.getElementById('notification-error-display');

    function showError(message) {
        errorDisplay.textContent = message;
        errorDisplay.style.display = 'block';
    }

    function handleFriendRequest(requestId, action) {
        // console.log(`Handling ${action} for request ID: ${requestId}`);
        fetch(`/friend_request/${action}/${requestId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errData => {
                    throw new Error(errData.error || 'Произошла ошибка при обработке запроса.');
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                const requestItem = document.getElementById(`request-${requestId}`);
                if (requestItem) {
                    requestItem.remove();
                }
                if (requestList && requestList.children.length === 0) {
                    const noRequestsMessage = document.getElementById('no-requests-message');
                    if (noRequestsMessage) {
                        noRequestsMessage.style.display = 'block';
                    }
                }
            } else {
                showError(data.error || 'Не удалось обработать запрос.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showError(error.message || 'Произошла ошибка сети.');
        });
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                let cookie = cookies[i].trim();
                if (cookie.startsWith(name + '=')) {
                    cookieValue = cookie.substring(name.length + 1);
                    break;
                }
            }
        }
        return cookieValue;
    }

    if (requestList) {
        requestList.addEventListener('click', (event) => {
            const target = event.target;
             const listItem = target.closest('.notification-item');
            if (!listItem) return;

            const requestId = listItem.dataset.requestId; //  Получаем из data-request-id
            const action = target.dataset.action;

            if (action === 'accept' || action === 'decline') {
                handleFriendRequest(requestId, action);
            }
        });
    }
});