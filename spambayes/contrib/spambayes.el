;; spambayes.el -- integrate spambayes into Gnus and VM
;; Copyright (C) 2003 Neale Pickett <neale@woozle.org>
;; Time-stamp: <2003-11-17 11:49:29 neale>

;; This is free software; you can redistribute it and/or modify it under
;; the terms of the GNU General Public License as published by the Free
;; Software Foundation; either version 2, or (at your option) any later
;; version.

;; This program is distributed in the hope that it will be useful, but
;; WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
;; General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with GNU Emacs; see the file COPYING.  If not, write to the
;; Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.

;; Purpose:
;;
;; Functions to put spambayes into Gnus and VM.

;; GNUS
;; ----
;; To install, just drop this file in your load path, and insert the
;; following lines in ~/.gnus:
;;
;; (setq gnus-sum-load-hook
;;   (lambda ()
;;     (require 'spambayes)
;;     (define-key gnus-summary-mode-map [(B) (s)] 'spambayes-gnus-refile-as-spam)
;;     (define-key gnus-summary-mode-map [(B) (h)] 'spambayes-gnus-refile-as-ham)))
;;
;; In summary mode, "B h" will train a message as ham and refile, and "B
;; s", appropriately enough, will train a message as spam and refile.
;; If you misfile something, simply locate it again and refile
;; it--sb_filter will know that you're retraining the message.
;;
;;
;; You can also put the following in ~/.gnus to run messages through the
;; filter as Gnus reads them in:
;;
;;  (setq nnmail-prepare-incoming-message-hook 'spambayes-filter-buffer)
;;
;; You can then use Gnus message splitting (looking at the
;; X-Spambayes-Classification header) to file messages based on the
;; spambayes score.
;;
;; Some folks may prefer using procmail to score messages when they
;; arrive.  See README.txt in the distribution for more information on
;; how to do this.




;; VM (Courtesy of Prabhu Ramachandran <prabhu@aero.iitm.ernet.in>)
;; ----
;; Put the following in ~/.vm:
;;
;; (load-library "spambayes")
;;
;; This binds "l h" to retrain processable messages as ham and "l s"
;; to retrain them as spam.
;; (define-key vm-mode-map "ls" 'spambayes-vm-retrain-as-spam)
;; (define-key vm-summary-mode-map "ls" 'spambayes-vm-retrain-as-spam)
;; (define-key vm-mode-map "lh" 'spambayes-vm-retrain-as-ham)
;; (define-key vm-summary-mode-map "lh" 'spambayes-vm-retrain-as-ham)
;;
;; (setq vm-auto-folder-alist
;;       '(("X-Spambayes-Classification:" ("spam" . "~/vmmail/SPAM"))
;;         ("X-Spambayes-Classification:" ("unsure" . "~/vmmail/UNSURE"))
;;         )
;; )
;;
;; Hitting the 'A' key will refile messages to the SPAM and UNSURE folders.
;;
;; The following visible header list might also be useful:
;; (setq vm-visible-headers
;;    '("Resent-"
;;      "From:" "Sender:" "Reply-To:"
;;      "To:" "Apparently-To:" "Cc:"
;;      "Subject:"
;;      "Date:"
;;      "X-Spambayes-Classification:"))


(defvar spambayes-filter-program "/usr/local/bin/sb_filter.py"
  "Path to the sb_filter program.")


;; Gnus

(defun spambayes-filter-buffer (&optional buffer)
  "Filter a buffer through Spambayes.

This pipes the a buffer through Spambayes, which adds its headers.  The
output of Spambayes replaces the contents of the buffer.  If no buffer
is specified, the current buffer is used.
"
  (shell-command-on-region
   (point-min)
   (point-max)
   (concat
    spambayes-filter-program
    " -f")
   (or buffer (current-buffer))
   t))

(defun spambayes-gnus-retrain (is-spam)
  "Retrain on all processable articles, or the one under the cursor.

This will replace the buffer contents with command output.  You can then
respool the article.

is-spam is a boolean--true if you want to retrain the message as spam,
false if you want to retrain as ham.
"
  (labels ((do-exec (n group is-spam)
		    (message "Retraining...")
		    (with-temp-buffer
		      (gnus-request-article-this-buffer n group)
		      (cond
		       ((zerop (shell-command-on-region
			       (point-min)
			       (point-max)
			       (concat
				spambayes-filter-program
				(if is-spam " -s" " -g")
				" -f")
			       (current-buffer)
			       t))
			(gnus-request-replace-article n group (current-buffer))
			(message "Retrained article."))
		       (t
			(message "Unable to parse article--leaving it alone."))))))
    (let ((group gnus-newsgroup-name)
	  (list gnus-newsgroup-processable))
      (if (>= (length list) 1)
	  (while list
	    (let ((n (car list)))
	      (do-exec n group is-spam))
	    (setq list (cdr list)))
	(let ((n (gnus-summary-article-number)))
	  (do-exec n group is-spam))))))

(defun spambayes-gnus-refile-as-spam ()
  "Retrain and refilter all process-marked messages as spam, then respool them"
  (interactive)
  (spambayes-gnus-retrain 't)
  (gnus-summary-respool-article nil (gnus-group-method gnus-newsgroup-name)))

(defun spambayes-gnus-refile-as-ham ()
  "Retrain and refilter all process-marked messages as ham, then respool them"
  (interactive)
  (spambayes-gnus-retrain nil)
  (gnus-summary-respool-article nil (gnus-group-method gnus-newsgroup-name)))



;;; VM

(defun spambayes-vm-retrain (is-spam)
  "Retrain on all processable articles, or the one under the cursor.

is-spam is a boolean--true if you want to retrain the message as spam,
false if you want to retrain as ham.
"
  (interactive)
  (message (concat "Retraining" (if is-spam " as SPAM" " as HAM") " ..."))
  (vm-pipe-message-to-command
   (concat spambayes-filter-program (if is-spam " -s" " -g") " -f") nil)
  (message (concat "Done retraining messages"
                   (if is-spam " as SPAM" " as HAM") ".") )
)

(defun spambayes-vm-retrain-as-spam ()
  "Retrain and refilter messages as spam"
  (interactive)
  (spambayes-vm-retrain t)
)

(defun spambayes-vm-retrain-as-ham ()
  "Retrain and refilter messages as ham"
  (interactive)
  (spambayes-vm-retrain nil)
)

(provide 'spambayes)
