# Firebase Google Login Integration (LuxSCale)

## 1) Create Firebase project and web app

1. Open [Firebase Console](https://console.firebase.google.com/) and create/select your project.
2. In **Project settings > General**, add a **Web app**.
3. Copy the Firebase config object (`apiKey`, `authDomain`, etc.).

## 2) Enable Google provider

1. Go to **Authentication > Sign-in method**.
2. Enable **Google** provider.
3. Set project support email and save.

## 3) Configure authorized domains

Add all domains used by LuxSCale frontend, for example:

- `localhost`
- `127.0.0.1`
- your production host/domain

## 4) Add Firebase SDK to frontend

Use the modular SDK in your frontend script:

```html
<script type="module">
  import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.0/firebase-app.js";
  import {
    getAuth,
    GoogleAuthProvider,
    signInWithPopup,
    signOut,
    onAuthStateChanged
  } from "https://www.gstatic.com/firebasejs/11.0.0/firebase-auth.js";

  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  const provider = new GoogleAuthProvider();
</script>
```

## 5) Sign in / sign out flow

1. On login click, call `signInWithPopup(auth, provider)`.
2. On success, read `user.uid`, `user.email`, `user.displayName`.
3. Save lightweight identity key for chat/session:
   - `localStorage["luxscale_firebase_uid"] = user.uid`
4. On logout, call `signOut(auth)` and clear identity keys.

## 6) Tie chat session to hybrid identity (Option 3)

Use:

- `uid` session when Google user exists (`session_id = "uid_" + uid`)
- fallback random anonymous `session_id` otherwise

Store chat history by identity key:

- `luxscale_chat_history_uid_<uid>` for logged users
- `luxscale_chat_history_<anon_session_id>` for anonymous users

If user logs in after chatting anonymously, copy anonymous history to UID key once.

## 7) Optional backend token verification (recommended for protected APIs)

For trusted operations:

1. Send Firebase ID token from frontend (`await user.getIdToken()`).
2. Verify in backend using Firebase Admin SDK.
3. Use verified `uid` server-side instead of trusting plain client payload.

## 8) Error handling and fallback UX

- If popup blocked or canceled, keep anonymous session active.
- If Firebase init fails, keep chat usable in anonymous mode.
- Show friendly message and retry action for auth/network errors.

## 9) Can Google emails be used for subscriber mailing?

Yes, but only with consent and compliance controls:

1. Get explicit opt-in (unchecked checkbox, clear wording).
2. Store proof of consent (timestamp, source page, policy version).
3. Include unsubscribe link in every email.
4. Honor unsubscribe quickly and permanently.
5. Follow applicable laws (GDPR, CAN-SPAM, local regulations).

## 10) Technical recommendation for mailing

- Use a mailing provider (Mailchimp, SendGrid, Brevo, etc.).
- Keep a subscriber table with:
  - `email`
  - `uid` (optional)
  - `consent_status`
  - `consent_timestamp`
  - `unsubscribed_at`
- Never subscribe users automatically just because they logged in.
