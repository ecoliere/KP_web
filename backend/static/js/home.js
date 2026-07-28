document.addEventListener('DOMContentLoaded', async () => {

    const loadingIndicator = document.getElementById('loading-indicator');
    const errorDisplay = document.getElementById('error-display');
    const profileHeader = document.querySelector('.profile-header');

    const profilePic = document.getElementById('profile-pic');
    const userFullname = document.getElementById('user-fullname');
    const userUsername = document.getElementById('user-username');

    const aboutSection = document.getElementById('profile-about-section');
    const userEmail = document.getElementById('user-email');
    const userRegDate = document.getElementById('user-reg-date');
    const userLastVisit = document.getElementById('user-last-visit');
    const userVisitCount = document.getElementById('user-visit-count');
    const userHobbies = document.getElementById('user-hobbies');

    const friendsSection = document.getElementById('friends-widget-section');
    const friendsList = document.getElementById('friends-list');
    const friendsCountSpan = document.getElementById('friends-count');
    const noFriendsMessage = document.getElementById('no-friends-message');

    const requestsSection = document.getElementById('friend-requests-section');
    const requestsList = document.getElementById('friend-requests-list');
    const requestsCountSpan = document.getElementById('requests-count');
    const noRequestsMessage = document.getElementById('no-requests-message');

    const createPostSection = document.getElementById('create-post-section');
    const postsFeedSection = document.getElementById('posts-feed-section');
    const postContentInput = document.getElementById('post-content-input');
    const publishPostButton = document.getElementById('publish-post-button'); // Используем это имя
    const postErrorDisplay = document.getElementById('post-error-display');
    const userPostsFeed = document.getElementById('user-posts-feed');
    const postsLoadingPlaceholder = document.getElementById('posts-loading-placeholder');
    const noPostsMessage = document.getElementById('no-posts-message');

    function displayError(message, containerId = 'error-display') {
        const errorDiv = document.getElementById(containerId);
        if (!errorDiv) {
            console.error(`Error display container with ID '${containerId}' not found.`);
            return;
        }
        errorDiv.textContent = `Ошибка: ${message}`;
        errorDiv.style.display = 'block';
        if (containerId === 'error-display' && loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
    }

    function formatDateTime(isoString) {
        if (!isoString) return 'Неизвестно';
        try {
            const date = new Date(isoString);
            if (isNaN(date.getTime())) {
                console.warn("Invalid date string for formatting:", isoString);
                return 'Некорректная дата';
            }
            // Используем более короткий формат для месяца, чтобы избежать слишком длинных строк
            const options = { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
            return date.toLocaleString('ru-RU', options);
        } catch (e) {
            console.error("Error formatting date:", e, "Input:", isoString);
            return 'Ошибка формата';
        }
    }

    function getProfilePicUrl(filename) {
        const basePath = "/static/uploads/";
        const defaultPicPath = "/static/images/default_avatar.png"; // Убедитесь, что этот файл существует
        return filename ? basePath + filename : defaultPicPath;
    }

    function checkEmptyList(listElement, messageElement, loadingPlaceholder) {
        if (!listElement || !messageElement) return;

        if (loadingPlaceholder && loadingPlaceholder.parentNode === listElement) {
            listElement.removeChild(loadingPlaceholder);
        }
        // Проверяем, есть ли дочерние элементы, которые не являются элементом сообщения "нет элементов"
        const realItems = Array.from(listElement.children).filter(child => child !== messageElement && !child.classList.contains('loading-placeholder'));
        messageElement.style.display = realItems.length > 0 ? 'none' : 'block';
    }


    async function handleFriendAction(action, targetUserId, buttonElement) {
        if (!action || !targetUserId || !buttonElement) return;

        buttonElement.disabled = true;
        const originalText = buttonElement.textContent;
        buttonElement.textContent = '...';

        // ВАЖНО: Убедитесь, что этот URL соответствует вашему API в app.py
        const apiUrl = `/api/friend/${action}/${targetUserId}`;
        const method = 'POST'; // Обычно для таких действий используется POST

        try {
            const response = await fetch(apiUrl, {
                method: method,
                headers: { 'Content-Type': 'application/json' }
                // body: JSON.stringify({}), // Если API требует тело, даже пустое
            });
            const result = await response.json();

            if (response.ok && result.success) {
                console.log(`${action} action successful for user ${targetUserId}`);
                const requestItem = buttonElement.closest('.widget-list-item');
                if (requestItem) {
                    requestItem.style.transition = 'opacity 0.3s ease-out';
                    requestItem.style.opacity = '0';
                    setTimeout(() => {
                        requestItem.remove();
                        if (requestsList && requestsCountSpan && noRequestsMessage) {
                            requestsCountSpan.textContent = requestsList.children.length;
                            checkEmptyList(requestsList, noRequestsMessage, null); // Передаем null т.к. placeholder уже удален
                        }
                        if (action === 'accept') { // Если заявка принята, обновляем список друзей
                            fetchFriendsData();
                        }
                    }, 300);
                }
            } else {
                console.error(`API Error (${action}):`, result.message || result.error || 'Unknown error');
                displayError(result.message || result.error || `Действие '${action}' не удалось.`);
                buttonElement.disabled = false;
                buttonElement.textContent = originalText;
            }
        } catch (error) {
            console.error(`Network or fetch error during ${action}:`, error);
            displayError(`Сетевая ошибка при действии '${action}'.`);
            buttonElement.disabled = false;
            buttonElement.textContent = originalText;
        }
    }

    async function fetchFriendRequests() {
        if (!requestsList || !requestsCountSpan || !noRequestsMessage || !requestsSection) return;

        const placeholder = requestsList.querySelector('.loading-placeholder');
        if (placeholder) placeholder.style.display = 'block'; // Показываем загрузчик
        noRequestsMessage.style.display = 'none';

        try {
            const response = await fetch('/api/user/me/friend-requests');
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const requests = await response.json();

            if (placeholder) requestsList.innerHTML = ''; // Очищаем только если был placeholder

            requestsCountSpan.textContent = requests.length;

            if (requests.length > 0) {
                requests.forEach(req => {
                    const item = document.createElement('li');
                    item.classList.add('widget-list-item');
                    const picUrl = getProfilePicUrl(req.profile_picture);
                    const picClass = req.profile_picture ? '' : 'default-pic';
                    item.innerHTML = `
                        <div class="item-avatar-name">
                            <img src="${picUrl}" alt="${req.username}" class="profile-pic-small ${picClass}">
                            <a href="/profile/${req.username}" class="item-name">${req.full_name || req.username}</a>
                        </div>
                        <div class="friend-actions">
                            <button class="btn-accept" data-user-id="${req.id}" data-action="accept">Принять</button>
                            <button class="btn-decline" data-user-id="${req.id}" data-action="decline">Отклонить</button>
                        </div>`;
                    requestsList.appendChild(item);
                });
            }
            checkEmptyList(requestsList, noRequestsMessage, null); // placeholder уже должен быть удален
            requestsSection.style.display = 'block';

        } catch (error) {
            console.error('Failed to fetch friend requests:', error);
            if (placeholder && placeholder.parentNode === requestsList) requestsList.innerHTML = ''; // Очищаем только если был placeholder
            displayError('Не удалось загрузить заявки в друзья.', 'error-display'); // Отображаем в главном блоке ошибок
            checkEmptyList(requestsList, noRequestsMessage, null);
            requestsSection.style.display = 'block';
        }
    }

    async function fetchFriendsData() {
        if (!friendsList || !friendsCountSpan || !noFriendsMessage || !friendsSection) return;

        const placeholder = friendsList.querySelector('.loading-placeholder');
        if (placeholder) placeholder.style.display = 'block';
        noFriendsMessage.style.display = 'none';

        try {
            const response = await fetch('/api/user/me/friends');
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const friends = await response.json();

            if (placeholder) friendsList.innerHTML = '';
            friendsCountSpan.textContent = friends.length;

            if (friends.length > 0) {
                friends.forEach(friend => {
                    const item = document.createElement('li');
                    item.classList.add('widget-list-item');
                    const picUrl = getProfilePicUrl(friend.profile_picture);
                    const picClass = friend.profile_picture ? '' : 'default-pic';
                    item.innerHTML = `
                        <div class="item-avatar-name">
                            <img src="${picUrl}" alt="${friend.username}" class="profile-pic-small ${picClass}">
                            <a href="/profile/${friend.username}" class="item-name">${friend.full_name || friend.username}</a>
                        </div>`;
                    friendsList.appendChild(item);
                });
            }
            checkEmptyList(friendsList, noFriendsMessage, null);
            friendsSection.style.display = 'block';

        } catch (error) {
            console.error('Failed to fetch friends:', error);
            if (placeholder && placeholder.parentNode === friendsList) friendsList.innerHTML = '';
            displayError('Не удалось загрузить список друзей.', 'error-display');
            checkEmptyList(friendsList, noFriendsMessage, null);
            friendsSection.style.display = 'block';
        }
    }

    function renderPost(post) {
        const postElement = document.createElement('article');
        postElement.classList.add('post-item'); // Этот класс должен быть стилизован как виджет
        postElement.dataset.postId = post.id;

        const authorPicUrl = getProfilePicUrl(post.profile_picture);
        const authorPicClass = post.profile_picture ? '' : 'default-pic';
        // Безопасное отображение контента, заменяя только переносы строк
        const formattedContent = (post.content || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;").replace(/\n/g, '<br>');
        const formattedTimestamp = post.created_at_formatted || formatDateTime(post.created_at_iso || post.created_at);

        postElement.innerHTML = `
            <div class="post-header">
                <img src="${authorPicUrl}" alt="${post.username}" class="profile-pic-small post-author-pic ${authorPicClass}">
                <div class="post-author-info">
                    <a href="/profile/${post.username}" class="post-author-name">${post.full_name || post.username}</a>
                    <span class="post-timestamp">${formattedTimestamp}</span>
                </div>
            </div>
            <div class="post-content">
                <p>${formattedContent}</p> 
            </div>`;
        return postElement;
    }

    async function fetchAndDisplayPosts() {
        if (!userPostsFeed || !noPostsMessage || !postsLoadingPlaceholder || !postsFeedSection) return;

        postsLoadingPlaceholder.style.display = 'block';
        noPostsMessage.style.display = 'none';
        userPostsFeed.innerHTML = ''; // Очищаем предыдущие посты перед загрузкой
        userPostsFeed.appendChild(postsLoadingPlaceholder); // Добавляем placeholder обратно

        try {
            const response = await fetch('/api/user/me/posts');
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const posts = await response.json();

            if (postsLoadingPlaceholder.parentNode === userPostsFeed) { // Удаляем placeholder только если он еще там
                 userPostsFeed.removeChild(postsLoadingPlaceholder);
            }
            userPostsFeed.innerHTML = ''; // Финальная очистка перед добавлением новых постов

            if (posts.length === 0) {
                userPostsFeed.appendChild(noPostsMessage);
                noPostsMessage.style.display = 'block';
            } else {
                noPostsMessage.style.display = 'none';
                posts.forEach(post => {
                    const postElement = renderPost(post);
                    userPostsFeed.appendChild(postElement);
                });
            }
            postsFeedSection.style.display = 'block';

        } catch (error) {
            console.error('Failed to fetch posts:', error);
            if (postsLoadingPlaceholder.parentNode === userPostsFeed) {
                 userPostsFeed.removeChild(postsLoadingPlaceholder);
            }
            userPostsFeed.innerHTML = ''; // Очищаем в случае ошибки
            const errorP = document.createElement('p');
            errorP.classList.add('error-message'); // Используйте ваш класс для ошибок
            errorP.textContent = 'Не удалось загрузить записи.';
            userPostsFeed.appendChild(errorP);
            noPostsMessage.style.display = 'none'; // Скрываем "нет постов", показываем ошибку
            postsFeedSection.style.display = 'block';
        }
    }

    async function publishPost() {
        if (!postContentInput || !publishPostButton || !postErrorDisplay) return;

        const content = postContentInput.value.trim();
        if (!content) {
            displayError('Пожалуйста, введите текст записи.', 'post-error-display');
            postContentInput.focus();
            return;
        }

        postErrorDisplay.style.display = 'none';
        publishPostButton.disabled = true;
        publishPostButton.textContent = 'Публикация...';

        try {
            const response = await fetch('/api/posts/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: content })
            });
            const result = await response.json();

            if (response.ok && result.success && result.post) {
                postContentInput.value = '';
                const newPostElement = renderPost(result.post);

                if (noPostsMessage.parentNode === userPostsFeed) { // Если было сообщение "нет постов"
                     userPostsFeed.removeChild(noPostsMessage);
                }
                // Вставляем новый пост в начало списка
                userPostsFeed.insertBefore(newPostElement, userPostsFeed.firstChild);

            } else {
                displayError(result.error || 'Не удалось опубликовать запись.', 'post-error-display');
            }
        } catch (error) {
            console.error('Failed to publish post:', error);
            displayError('Сетевая ошибка при публикации.', 'post-error-display');
        } finally {
            publishPostButton.disabled = false; // ИСПРАВЛЕНО: publishPostButton вместо publishButton
            publishPostButton.textContent = 'Опубликовать';
        }
    }

    // Показываем основные секции после того как DOM загружен (если они не скрыты по умолчанию в CSS)
    if (profileHeader) profileHeader.style.visibility = 'visible';
    if (aboutSection) aboutSection.style.display = 'block';
    // Остальные секции (friends, requests, posts) будут показаны после загрузки их данных

    // Инициализация: загрузка данных
    if (loadingIndicator) loadingIndicator.style.display = 'block'; // Показываем главный загрузчик

    try {
        const response = await fetch('/api/user/me');
        if (!response.ok) {
            if (response.status === 401) { // Не авторизован
                window.location.href = '/login'; // Перенаправляем на страницу входа
                return; // Прекращаем выполнение скрипта
            }
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const userData = await response.json();

        // Заполнение шапки профиля
        if (userFullname) userFullname.textContent = userData.full_name || userData.username;
        if (userUsername) userUsername.textContent = `@${userData.username}`;
        if (profilePic) {
            const picUrl = getProfilePicUrl(userData.profile_picture);
            profilePic.src = picUrl;
            profilePic.alt = `${userData.username}'s profile picture`;
            profilePic.classList.toggle('default-pic', !userData.profile_picture);
            profilePic.onerror = () => { // Обработка ошибки загрузки основного изображения
                profilePic.src = getProfilePicUrl(null); // Ставим дефолтное
                profilePic.classList.add('default-pic');
            };
        }

        // Заполнение секции "Информация"
        if (userEmail) userEmail.textContent = userData.email || 'Не указан';
        if (userRegDate) userRegDate.textContent = formatDateTime(userData.registration_date);
        if (userLastVisit) userLastVisit.textContent = formatDateTime(userData.last_visit);
        if (userVisitCount) userVisitCount.textContent = userData.visit_count != null ? userData.visit_count : '0';
        if (userHobbies) userHobbies.textContent = userData.hobbies || 'Не указаны';
        // Убираем класс .loading-placeholder из текстовых спанов в информации
        document.querySelectorAll('#profile-about-section .loading-placeholder').forEach(el => {
            if (el.textContent === '...') el.textContent = 'Не указано'; // Если JS не успел заменить
            el.classList.remove('loading-placeholder');
        });


        // Параллельная загрузка списков
        await Promise.all([
            fetchFriendRequests(),
            fetchFriendsData(),
            fetchAndDisplayPosts()
        ]);

    } catch (error) {
        console.error('Failed to load initial profile data:', error);
        displayError('Не удалось загрузить данные профиля. Пожалуйста, обновите страницу.');
        // Можно скрыть все секции, если основная загрузка не удалась
        if (profileHeader) profileHeader.style.display = 'none';
        if (aboutSection) aboutSection.style.display = 'none';
        if (friendsSection) friendsSection.style.display = 'none';
        if (requestsSection) requestsSection.style.display = 'none';
        if (createPostSection) createPostSection.style.display = 'none';
        if (postsFeedSection) postsFeedSection.style.display = 'none';
    } finally {
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    // Навешиваем обработчики событий
    if (publishPostButton) {
        publishPostButton.addEventListener('click', publishPost);
    }

    if (requestsList) {
        requestsList.addEventListener('click', (event) => {
            const target = event.target;
            // Убедимся, что клик был по кнопке внутри .friend-actions
            if (target.tagName === 'BUTTON' && target.closest('.friend-actions') && target.dataset.action) {
                const action = target.dataset.action;
                const userId = target.dataset.userId;
                if (action && userId) {
                    handleFriendAction(action, userId, target);
                }
            }
        });
    }
});