;; spambayes.el -- integrate spambayes into Gnus
;; Copyright (C) 2003 Neale Pickett <neale@woozle.org>
;; Time-stamp: <2003-01-27 13:12:14 neale>

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
;; Functions to put spambayes into Gnus.  
;;
;; This assumes you are already filtering with a procmail recipie
;; similar to:
;;
;;   :0fw
;;   | hammiefilter.py -t
;;
;; If you can't run procmail on all your incoming messages, you shold
;; have a look at spam.el, which is included with Oort Gnus.
;;
;; This binds "B s" to "refile as spam", and "B h" to "refile as ham".
;; After refiling, the message is rescored and respooled.  I haven't yet
;; run across a case where refiling doesn't change a message's score
;; well into the ham or spam range.  If this happens to you, please let
;; me know.

;; Installation:
;;
;; To install, just drop this file in your load path, and insert the
;; following lines in ~/.gnus:
;;
;; (load-library "spambayes")
;; (add-hook
;;  'gnus-sum-load-hook
;;  (lambda nil
;;    (define-key gnus-summary-mode-map [(B) (s)] 'spambayes-refile-as-spam)
;;    (define-key gnus-summary-mode-map [(B) (h)] 'spambayes-refile-as-ham)))
;;

(defvar spambayes-spam-group "spam"
  "Group name for spam messages")

(defvar spambayes-hammiefilter "~/src/spambayes/hammiefilter.py"
  "Path to the hammiefilter program")

(defun spambayes-retrain (is-spam)
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
		      (shell-command-on-region
		       (point-min)
		       (point-max)
		       (concat
			spambayes-hammiefilter
			(if is-spam " -s" " -g")
			" -f")
		       (current-buffer)
		       t)
		      (gnus-request-replace-article n group (current-buffer)))
		    (message "Retrained article.")))
    (let ((group gnus-newsgroup-name)
	  (list gnus-newsgroup-processable))
      (if (>= (length list) 1)
	  (while list
	    (let ((n (car list)))
	      (do-exec n group is-spam))
	    (setq list (cdr list)))
	(let ((n (gnus-summary-article-number)))
	  (do-exec n group is-spam))))))

(defun spambayes-refile-as-spam ()
  "Retrain and refilter all process-marked messages as spam, then respool them"
  (interactive)
  (spambayes-retrain 't)
  (gnus-summary-respool-article nil (gnus-group-method gnus-newsgroup-name)))

(defun spambayes-refile-as-ham ()
  "Retrain and refilter all process-marked messages as ham, then respool them"
  (interactive)
  (spambayes-retrain nil)
  (gnus-summary-respool-article nil (gnus-group-method gnus-newsgroup-name)))

