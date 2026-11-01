package com.financetracker.access.web;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.access.application.AuthService;
import com.financetracker.access.application.MeService;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.security.CurrentUser;
import com.financetracker.shared.web.Throttler;

/** /api/v1/auth/* (api/views/auth.py). */
@RestController
@RequestMapping("/api/v1/auth")
class AuthController {

    private final AuthService auth;
    private final MeService me;
    private final Throttler throttler;
    private final AppProperties props;

    AuthController(AuthService auth, MeService me, Throttler throttler, AppProperties props) {
        this.auth = auth;
        this.me = me;
        this.throttler = throttler;
        this.props = props;
    }

    @PostMapping("/register/")
    ResponseEntity<Map<String, Object>> register(@RequestBody(required = false) Map<String, Object> body,
            HttpServletRequest request) {
        throttler.check("auth_register", props.getThrottle().getAuthRegister(), Throttler.ident(request));
        return ResponseEntity.status(HttpStatus.CREATED).body(auth.register(body));
    }

    @PostMapping("/login/")
    Map<String, Object> login(@RequestBody(required = false) Map<String, Object> body, HttpServletRequest request) {
        throttler.check("auth_login", props.getThrottle().getAuthLogin(), Throttler.ident(request));
        return auth.login(body);
    }

    @PostMapping("/token/refresh/")
    Map<String, Object> refresh(@RequestBody(required = false) Map<String, Object> body) {
        return auth.refresh(body);
    }

    @PostMapping("/logout/")
    ResponseEntity<Void> logout(@RequestBody(required = false) Map<String, Object> body) {
        auth.logout(body);
        return ResponseEntity.noContent().build();
    }

    @GetMapping(value = "/email-verify/confirm/", produces = MediaType.TEXT_HTML_VALUE)
    String confirmEmailPage(@RequestParam(defaultValue = "") String uid, @RequestParam(defaultValue = "") String token) {
        return auth.confirmEmailPage(uid, token);
    }

    @PostMapping("/email-verify/confirm/")
    Map<String, Object> confirmEmail(@RequestBody(required = false) Map<String, Object> body) {
        return auth.confirmEmail(body);
    }

    @PostMapping("/email-verify/resend/")
    Map<String, Object> resend(@RequestBody(required = false) Map<String, Object> body, HttpServletRequest request) {
        throttler.check("auth_email", props.getThrottle().getAuthEmail(), Throttler.ident(request));
        return auth.resendVerification(body, CurrentUser.get());
    }

    @PostMapping("/password-reset/")
    Map<String, Object> passwordReset(@RequestBody(required = false) Map<String, Object> body,
            HttpServletRequest request) {
        throttler.check("auth_email", props.getThrottle().getAuthEmail(), Throttler.ident(request));
        return auth.requestPasswordReset(body);
    }

    @GetMapping(value = "/password-reset/open/", produces = MediaType.TEXT_HTML_VALUE)
    String passwordResetOpen(@RequestParam(defaultValue = "") String uid, @RequestParam(defaultValue = "") String token) {
        return auth.passwordResetOpenPage(uid, token);
    }

    @PostMapping("/password-reset/confirm/")
    Map<String, Object> passwordResetConfirm(@RequestBody(required = false) Map<String, Object> body,
            HttpServletRequest request) {
        throttler.check("auth_login", props.getThrottle().getAuthLogin(), Throttler.ident(request));
        return auth.confirmPasswordReset(body);
    }

    @PostMapping("/firebase/")
    Map<String, Object> firebase(@RequestBody(required = false) Map<String, Object> body, HttpServletRequest request) {
        throttler.check("auth_login", props.getThrottle().getAuthLogin(), Throttler.ident(request));
        return auth.firebaseLogin(body);
    }

    @GetMapping("/me/")
    Map<String, Object> me(@RequestParam(required = false) String tz, @RequestParam(required = false) String locale,
            @RequestParam(required = false) String country) {
        return me.get(CurrentUser.require(), tz, locale, country);
    }

    /** RetrieveUpdateAPIView: PUT and PATCH both apply a partial update here. */
    @PatchMapping("/me/")
    Map<String, Object> patchMe(@RequestBody(required = false) Map<String, Object> body) {
        return me.update(CurrentUser.require(), body);
    }

    @PutMapping("/me/")
    Map<String, Object> putMe(@RequestBody(required = false) Map<String, Object> body) {
        return me.update(CurrentUser.require(), body);
    }
}
